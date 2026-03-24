from __future__ import annotations

import asyncio
import logging
import time

from bot.client import SimulatorClient, make_session
from bot.config import BotConfig
from bot.fair_value import recompute_fair_values
from bot.models import BotState, BookLevel, Contract, OpenOrder, OrderBook
from bot.bracket_source import BracketSource
from bot.probability_source import ProbabilitySource
from bot.live_odds import LiveOddsSource
from bot.reporting import append_fills, write_fair_values, write_open_orders, write_positions
from bot.state import (
    apply_book_update,
    apply_bracket_update,
    apply_fill_event,
    apply_fv_update,
    apply_order_event,
    apply_position_snapshot,
)
from bot.strategy_arbitrage import build_basket_arb_orders, build_eliminated_mispricing_orders
from bot.strategy_live import build_live_dislocation_orders

logger = logging.getLogger(__name__)


class TradingBotApp:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.state = BotState()
        self._fills_written_index = 0

    async def run(self) -> None:
        async with make_session() as session:
            client = SimulatorClient(
                session=session,
                game_id=self.config.game_id,
                token=self.config.token,
                base_url=self.config.base_url,
            )
            bracket_source = BracketSource(session)
            prob_source = ProbabilitySource(session, self.config.playoff_status_url)
            live_source = LiveOddsSource(session, self.config.odds_api_base, self.config.odds_api_key)

            await self._startup_sync(client, bracket_source, prob_source, live_source)

            tasks = [
                asyncio.create_task(client.start()),
                asyncio.create_task(self._book_poll_loop(client)),
                asyncio.create_task(self._account_resync_loop(client)),
                asyncio.create_task(self._bracket_loop(bracket_source)),
                asyncio.create_task(self._probability_loop(prob_source)),
                asyncio.create_task(self._live_odds_loop(live_source)),
                asyncio.create_task(self._strategy_loop(client)),
                asyncio.create_task(self._event_consumer_loop(client)),
            ]
            try:
                await asyncio.gather(*tasks)
            finally:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _startup_sync(
        self,
        client: SimulatorClient,
        bracket_source: BracketSource,
        prob_source: ProbabilitySource,
        live_source: LiveOddsSource,
    ) -> None:
        contracts = await client.get_contracts()
        self.state.contracts = {
            contract_id: Contract(**row) for contract_id, row in contracts.items()
        }
        self.state.team_to_contract = {
            contract.normalized_team_name: contract.contract_id for contract in self.state.contracts.values()
        }

        await self._refresh_positions_orders_books(client)

        bracket = await bracket_source.fetch_states()
        for b in bracket.values():
            apply_bracket_update(self.state, b)

        self.state.baseline_probs = await prob_source.fetch_probabilities()
        self.state.touch("playoff_status", time.time())

        self.state.live_games = await live_source.fetch_live_probs()
        self.state.touch("live_odds", time.time())

        for fv in recompute_fair_values(self.state):
            apply_fv_update(self.state, fv)

        self._write_reports()

    async def _refresh_positions_orders_books(self, client: SimulatorClient) -> None:
        positions = await client.get_positions_snapshot()
        apply_position_snapshot(self.state, positions)
        self.state.server_cash = client.cash
        self.state.server_margin = client.margin

        orders = await client.get_open_orders()
        self.state.open_orders = {}
        for order_id, order in orders.items():
            side = "buy" if order.qty > 0 else "sell"
            apply_order_event(
                self.state,
                OpenOrder(order_id=order_id, contract_id=order.display_symbol, side=side, price=order.px, qty=abs(order.qty)),
            )

        books = await client.get_order_books()
        for contract_id, book in books.items():
            parsed = OrderBook(
                contract_id=contract_id,
                timestamp=book.timestamp,
                bids=tuple(BookLevel(price=px, qty=qty) for px, qty in sorted(book.bids.items(), key=lambda kv: kv[0], reverse=True)),
                asks=tuple(BookLevel(price=px, qty=qty) for px, qty in sorted(book.asks.items(), key=lambda kv: kv[0])),
            )
            apply_book_update(self.state, parsed)

        fills = await client.get_fills()
        for fill in fills:
            apply_fill_event(self.state, fill)

    async def _book_poll_loop(self, client: SimulatorClient) -> None:
        while True:
            try:
                books = await client.get_order_books()
                for contract_id, book in books.items():
                    parsed = OrderBook(
                        contract_id=contract_id,
                        timestamp=book.timestamp,
                        bids=tuple(BookLevel(price=px, qty=qty) for px, qty in sorted(book.bids.items(), key=lambda kv: kv[0], reverse=True)),
                        asks=tuple(BookLevel(price=px, qty=qty) for px, qty in sorted(book.asks.items(), key=lambda kv: kv[0])),
                    )
                    apply_book_update(self.state, parsed)
            except Exception as exc:
                logger.warning("book poll failed: %s", exc)
            await asyncio.sleep(self.config.intervals.books_seconds)

    async def _account_resync_loop(self, client: SimulatorClient) -> None:
        while True:
            try:
                await self._refresh_positions_orders_books(client)
                self._write_reports()
            except Exception as exc:
                logger.warning("account resync failed: %s", exc)
            await asyncio.sleep(self.config.intervals.account_seconds)

    async def _bracket_loop(self, source: BracketSource) -> None:
        while True:
            bracket = await source.fetch_states()
            for b in bracket.values():
                apply_bracket_update(self.state, b)
            for fv in recompute_fair_values(self.state):
                apply_fv_update(self.state, fv)
            self._write_reports()
            has_live = bool(self.state.live_games)
            delay = self.config.intervals.bracket_seconds_live if has_live else self.config.intervals.bracket_seconds_idle
            await asyncio.sleep(delay)

    async def _probability_loop(self, source: ProbabilitySource) -> None:
        while True:
            probs = await source.fetch_probabilities()
            if probs:
                self.state.baseline_probs = probs
                self.state.touch("playoff_status", time.time())
                for fv in recompute_fair_values(self.state):
                    apply_fv_update(self.state, fv)
                self._write_reports()
            await asyncio.sleep(self.config.intervals.playoff_status_seconds)

    async def _live_odds_loop(self, source: LiveOddsSource) -> None:
        while True:
            live = await source.fetch_live_probs()
            self.state.live_games = live
            self.state.touch("live_odds", time.time())
            for fv in recompute_fair_values(self.state):
                apply_fv_update(self.state, fv)
            self._write_reports()
            await asyncio.sleep(self.config.intervals.live_odds_seconds)

    async def _strategy_loop(self, client: SimulatorClient) -> None:
        while True:
            orders = []
            orders.extend(build_eliminated_mispricing_orders(self.state, self.config))
            orders.extend(build_basket_arb_orders(self.state, self.config))
            orders.extend(build_live_dislocation_orders(self.state, self.config))

            if orders:
                logger.info("strategy generated %d orders", len(orders))
            for order in orders:
                try:
                    if self.config.dry_run:
                        logger.info("DRY_RUN %s", order)
                        continue
                    await client.place_order(
                        contract_id=order.contract_id,
                        side=order.side,
                        price=order.price,
                        qty=order.qty,
                        tif="GTC",
                        post_only=False,
                    )
                except Exception as exc:
                    logger.warning("order failed %s: %s", order, exc)
            await asyncio.sleep(0.5)

    async def _event_consumer_loop(self, client: SimulatorClient) -> None:
        while True:
            try:
                while not client.fill_queue.empty():
                    fills = await client.fill_queue.get()
                    for fill in fills:
                        apply_fill_event(self.state, fill)
                while not client.order_queue.empty():
                    update = await client.order_queue.get()
                    side = "buy" if update.qty > 0 else "sell"
                    apply_order_event(
                        self.state,
                        OpenOrder(
                            order_id=update.order_id,
                            contract_id=update.display_symbol,
                            side=side,
                            price=update.px,
                            qty=abs(update.qty),
                        ),
                    )
                self._write_reports()
            except Exception as exc:
                logger.warning("event consume failed: %s", exc)
            await asyncio.sleep(0.25)

    def _write_reports(self) -> None:
        write_positions(self.state, self.config.csv.positions_path)
        write_open_orders(self.state, self.config.csv.open_orders_path)
        self._fills_written_index = append_fills(self.state, self.config.csv.fills_path, self._fills_written_index)
        write_fair_values(self.state, self.config.csv.fair_values_path)
