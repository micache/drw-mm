from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

import aiohttp

from bot import config
from bot.fair_value_engine import FairValueEngine
from bot.live_odds_source import LiveOddsSource
from bot.ncaa_source import NcaaSource
from bot.playoffstatus_source import PlayoffStatusSource
from bot.reporter import Reporter
from bot.risk_engine import RiskEngine
from bot.simulator_adapter import SimulatorAdapter
from bot.state_store import StateStore
from bot.strategy_arbitrage import ArbitrageStrategy
from bot.strategy_live import LiveStrategy
from bot.strategy_router import StrategyRouter
from bot.team_mapping import TeamMapper
from bot.models import FillView, LiveGameProb, OrderBook, OrderView

ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "trading-simulator-client"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from trading_client import Client  # type: ignore

logger = logging.getLogger(__name__)


class SimulatorBot(Client):
    def __init__(self, session: aiohttp.ClientSession, game_id: int, token: str, base_url: str = config.BASE_URL) -> None:
        super().__init__(session=session, game_id=game_id, token=token, base_url=base_url)
        self.mapper = TeamMapper()
        self.state_store = StateStore()
        self.adapter = SimulatorAdapter(self)
        self.ncaa_source = NcaaSource(session, config.NCAA_API_BASE, self.mapper)
        self.playoff_source = PlayoffStatusSource(session, config.PLAYOFFSTATUS_URL, self.mapper)
        self.live_odds_source = LiveOddsSource(session, config.ODDS_API_BASE, config.ODDS_API_KEY, config.ODDS_SPORT_KEY, self.mapper)
        self.fv_engine = FairValueEngine()
        self.reporter = Reporter()
        risk = RiskEngine()
        self.router = StrategyRouter(ArbitrageStrategy(risk), LiveStrategy(risk))
        self._strategy_event = asyncio.Event()

    async def on_start(self) -> None:
        try:
            await self.register()
        except Exception:
            logger.info("register skipped/fail; continuing")

        positions, orders, books = await self.adapter.bootstrap()
        self.state_store.apply_account_snapshot(self.cash, self.margin, positions)
        self.state_store.apply_open_orders_snapshot(orders)
        self.state_store.apply_orderbook_snapshot(books)

        contracts = self.adapter.contracts_from_books(books)
        for symbol, meta in contracts.items():
            self.mapper.register_symbol(symbol, meta.team_name)
        self.state_store.state.contracts = contracts

        await self._refresh_external_sources()
        self._recompute_fair_values()
        self.reporter.write_all(self.state_store.state)

        tasks = [
            asyncio.create_task(self._account_resync_loop()),
            asyncio.create_task(self._ncaa_refresh_loop()),
            asyncio.create_task(self._playoff_refresh_loop()),
            asyncio.create_task(self._live_odds_refresh_loop()),
            asyncio.create_task(self._reporter_loop()),
            asyncio.create_task(self._strategy_loop()),
        ]
        await asyncio.gather(*tasks)

    async def on_notification(self, message: str) -> None:
        logger.info("notification: %s", message)

    async def on_error(self, error: str) -> None:
        logger.error("server error: %s", error)

    async def on_fills(self, new_fills) -> None:
        for f in new_fills:
            fill = FillView(
                timestamp=f.timestamp,
                order_id=int(f.order_id),
                display_symbol=f.display_symbol,
                team_name=self.state_store.state.contracts.get(f.display_symbol).team_name if f.display_symbol in self.state_store.state.contracts else f.display_symbol,
                price=f.px,
                traded_qty=f.traded_qty,
                remaining_qty=f.remaining_qty,
            )
            self.state_store.apply_fill(fill)
        self._strategy_event.set()

    async def on_orderbook_updates(self, order_books) -> None:
        # The base client already maintains merged full books; we rely on periodic
        # adapter snapshots for canonical dataclass conversion.
        _ = order_books
        self.state_store.state.set_source_timestamp("books", time.time())
        self.state_store.state.mark_dirty("books")
        self._strategy_event.set()

    async def on_all_trade(self, trade) -> None:
        self.state_store.apply_trade()

    async def on_order_update(self, order) -> None:
        view = OrderView(
            order_id=order.order_id,
            display_symbol=order.display_symbol,
            team_name=self.state_store.state.contracts.get(order.display_symbol).team_name if order.display_symbol in self.state_store.state.contracts else order.display_symbol,
            side="buy" if order.qty > 0 else "sell",
            price=order.px,
            qty_signed=order.qty,
            qty_abs=abs(order.qty),
            canceled=order.canceled,
            last_updated_ts=time.time(),
        )
        self.state_store.apply_order_update(view)

    async def _account_resync_loop(self) -> None:
        while True:
            positions = await self.adapter.sync_positions()
            orders = await self.adapter.sync_open_orders()
            books = await self.adapter.sync_order_books()
            self.state_store.apply_account_snapshot(self.cash, self.margin, positions)
            self.state_store.apply_open_orders_snapshot(orders)
            self.state_store.apply_orderbook_snapshot(books)
            self._strategy_event.set()
            await asyncio.sleep(config.ACCOUNT_RESYNC_SECONDS)

    async def _ncaa_refresh_loop(self) -> None:
        while True:
            scoreboard = await self.ncaa_source.fetch_scoreboard()
            team_states = self.ncaa_source.refresh_team_live_status(scoreboard)
            self.state_store.apply_team_states(team_states)
            self._recompute_fair_values()
            self._strategy_event.set()
            delay = config.NCAA_REFRESH_LIVE_SECONDS if any(x.in_live_game for x in team_states.values()) else config.NCAA_REFRESH_IDLE_SECONDS
            await asyncio.sleep(delay)

    async def _playoff_refresh_loop(self) -> None:
        while True:
            probs = await self.playoff_source.refresh()
            self.state_store.apply_probabilities(probs)
            self._recompute_fair_values()
            self._strategy_event.set()
            await asyncio.sleep(config.PLAYOFFSTATUS_REFRESH_SECONDS)

    async def _live_odds_refresh_loop(self) -> None:
        while True:
            raws = await self.live_odds_source.fetch_live_games_odds()
            live: dict[str, LiveGameProb] = {}
            for raw in raws:
                parsed = self.live_odds_source.extract_moneyline_probs(raw)
                if not parsed:
                    continue
                live[parsed.game_id] = parsed
            self.state_store.apply_live_game_probs(live)
            self._recompute_fair_values()
            self._strategy_event.set()
            await asyncio.sleep(config.LIVE_ODDS_REFRESH_SECONDS)

    async def _reporter_loop(self) -> None:
        while True:
            if self.state_store.state.dirty_flags:
                self.reporter.write_all(self.state_store.state)
                self.state_store.state.dirty_flags.clear()
            await asyncio.sleep(config.CSV_DEBOUNCE_SECONDS)

    async def _strategy_loop(self) -> None:
        while True:
            await self._strategy_event.wait()
            self._strategy_event.clear()
            orders = self.router.evaluate(self.state_store.state)
            for o in orders:
                if config.DRY_RUN:
                    logger.info("DRY_RUN order=%s", o)
                    continue
                if o.side == "buy":
                    await self.adapter.place_bid(o.symbol, o.price, o.qty)
                else:
                    await self.adapter.place_ask(o.symbol, o.price, o.qty)

    async def _refresh_external_sources(self) -> None:
        scoreboard = await self.ncaa_source.fetch_scoreboard()
        self.state_store.apply_team_states(self.ncaa_source.refresh_team_live_status(scoreboard))
        self.state_store.apply_probabilities(await self.playoff_source.refresh())

    def _recompute_fair_values(self) -> None:
        self.state_store.apply_fair_values(self.fv_engine.recompute_all(self.state_store.state))
