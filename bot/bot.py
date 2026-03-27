from __future__ import annotations

import asyncio
import csv
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
from bot.pnl_engine import PnlEngine
from bot.reporter import Reporter
from bot.risk_engine import RiskEngine
from bot.simulator_adapter import SimulatorAdapter
from bot.state_store import StateStore
from bot.strategy_arbitrage import ArbitrageStrategy
from bot.strategy_live import LiveStrategy
from bot.strategy_pregame import PregameStrategy
from bot.inventory_reduction import InventoryReductionStrategy
from bot.strategy_router import StrategyRouter
from bot.team_mapping import TeamMapper, validate_symbol_mapping
from bot.models import ContractMeta, FillView, LiveGameProb, OrderBook, OrderView

ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "trading-simulator-client"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from trading_client import Client  # type: ignore

logger = logging.getLogger(__name__)


class SimulatorBot(Client):
    def __init__(
        self,
        session: aiohttp.ClientSession,
        game_id: int,
        token: str,
        base_url: str = config.BASE_URL,
        use_betting_odds: bool = False,
    ) -> None:
        super().__init__(session=session, game_id=game_id, token=token, base_url=base_url)
        self.use_betting_odds = use_betting_odds
        self.mapper = TeamMapper()
        self.state_store = StateStore()
        self.adapter = SimulatorAdapter(self)
        self.ncaa_source = NcaaSource(session, config.NCAA_API_BASE, self.mapper)
        self.playoff_source = PlayoffStatusSource(session, config.PLAYOFFSTATUS_URL, self.mapper)
        self.live_odds_source = LiveOddsSource(session, config.ODDS_API_BASE, config.ODDS_API_KEY, config.ODDS_SPORT_KEY, self.mapper)
        self.fv_engine = FairValueEngine()
        self.reporter = Reporter()
        self.pnl_engine = PnlEngine()
        risk = RiskEngine()
        self.router = StrategyRouter(ArbitrageStrategy(risk), PregameStrategy(risk), LiveStrategy(risk), InventoryReductionStrategy(risk))
        self._strategy_event = asyncio.Event()

    async def on_start(self) -> None:
        try:
            await self.register()
        except Exception:
            logger.info("register skipped/fail; continuing")

        logger.info("bootstrapping simulator snapshots...")
        cash, margin, positions, total_pnl, avg_entries = await self.adapter.sync_account()
        orders = await self.adapter.sync_open_orders()
        books = await self.adapter.sync_order_books()
        logger.info("bootstrap complete: positions=%d orders=%d books=%d", len(positions), len(orders), len(books))
        self.state_store.apply_account_snapshot(cash, margin, positions, total_pnl=total_pnl, avg_entries=avg_entries)
        self.state_store.apply_open_orders_snapshot(orders)
        self.state_store.apply_orderbook_snapshot(books)

        raw_contracts = self.adapter.contracts_from_books(books)
        contracts: dict[str, ContractMeta] = {}
        for symbol, meta in raw_contracts.items():
            norm = self.mapper.normalize(meta.team_name)
            self.mapper.register_symbol(symbol, meta.team_name)
            contracts[symbol] = ContractMeta(
                display_symbol=meta.display_symbol,
                team_name=meta.team_name,
                normalized_team_name=norm,
                seed=meta.seed,
                region=meta.region,
            )
        self.state_store.state.contracts = contracts
        await self._seed_pnl_from_fill_history()
        self._backfill_missing_avg_entries_from_mark()

        try:
            await asyncio.wait_for(self._refresh_external_sources(), timeout=12)
        except asyncio.TimeoutError:
            logger.warning("external source refresh timed out during startup; continuing")
        self._validate_mappings()
        self._recompute_fair_values()
        logger.info("startup fair values count=%d dry_run=%s", len(self.state_store.state.fair_values), config.DRY_RUN)
        self.reporter.write_all(self.state_store.state)
        self._strategy_event.set()

        tasks = [
            asyncio.create_task(self._account_resync_loop()),
            asyncio.create_task(self._ncaa_refresh_loop()),
            asyncio.create_task(self._playoff_refresh_loop()),
            asyncio.create_task(self._reporter_loop()),
            asyncio.create_task(self._strategy_loop()),
            asyncio.create_task(self._account_log_loop()),
        ]
        if self.use_betting_odds:
            tasks.append(asyncio.create_task(self._live_odds_refresh_loop()))
        else:
            logger.info("betting odds disabled; running without live odds source")
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

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
            self.pnl_engine.apply_fill(fill, self.state_store.state)
        self._strategy_event.set()

    async def on_orderbook_updates(self, order_books) -> None:
        # The base client already maintains merged full books; we rely on periodic
        # adapter snapshots for canonical dataclass conversion.
        _ = order_books
        self.state_store.state.set_source_timestamp("books", time.time())
        self.state_store.state.mark_dirty("books")
        self._strategy_event.set()

    async def on_all_trade(self, trade) -> None:
        self.state_store.apply_trade(trade.display_symbol, trade.px)

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
            try:
                cash, margin, positions, total_pnl, avg_entries = await self.adapter.sync_account()
                orders = await self.adapter.sync_open_orders()
                books = await self.adapter.sync_order_books()
                self.state_store.apply_account_snapshot(cash, margin, positions, total_pnl=total_pnl, avg_entries=avg_entries)
                self.state_store.apply_open_orders_snapshot(orders)
                self.state_store.apply_orderbook_snapshot(books)
                self._backfill_missing_avg_entries_from_mark()
                self._strategy_event.set()
            except Exception as exc:
                logger.warning("account resync failed: %s", exc)
            await asyncio.sleep(config.ACCOUNT_RESYNC_SECONDS)

    async def _ncaa_refresh_loop(self) -> None:
        while True:
            delay = config.NCAA_SCOREBOARD_REFRESH_SECONDS
            try:
                scoreboard = await self.ncaa_source.fetch_scoreboard()
                live_states = self.ncaa_source.refresh_live_games(scoreboard)
                bracket = await self.ncaa_source.fetch_bracket()
                team_states = self.ncaa_source.refresh_bracket_truth(bracket, live_states)
                self.state_store.apply_team_states(team_states)
                self._recompute_fair_values()
                self._strategy_event.set()
                delay = config.NCAA_SCOREBOARD_REFRESH_SECONDS
            except Exception as exc:
                logger.warning("ncaa refresh failed: %s", exc)
            await asyncio.sleep(delay)

    async def _playoff_refresh_loop(self) -> None:
        while True:
            try:
                probs = await self.playoff_source.refresh()
                self.state_store.apply_probabilities(probs)
                self._recompute_fair_values()
                self._strategy_event.set()
            except Exception as exc:
                logger.warning("playoff refresh failed: %s", exc)
            await asyncio.sleep(config.PLAYOFFSTATUS_REFRESH_SECONDS)

    async def _live_odds_refresh_loop(self) -> None:
        while True:
            try:
                if not self._should_poll_live_odds(time.time()):
                    await asyncio.sleep(config.LIVE_ODDS_IDLE_SECONDS)
                    continue
                raws = await self.live_odds_source.fetch_games_odds()
                live: dict[str, LiveGameProb] = {}
                for raw in raws:
                    parsed = self.live_odds_source.extract_moneyline_probs(raw)
                    if not parsed:
                        continue
                    live[parsed.game_id] = parsed
                self.state_store.apply_live_game_probs(live)
                if raws:
                    logger.info("live odds refresh: raw_games=%d parsed_games=%d", len(raws), len(live))
                self._recompute_fair_values()
                self._strategy_event.set()
            except Exception as exc:
                logger.warning("live odds refresh failed: %s", exc)
            await asyncio.sleep(config.LIVE_ODDS_REFRESH_SECONDS)

    async def _reporter_loop(self) -> None:
        while True:
            if self.state_store.state.dirty_flags:
                self.reporter.write_all(self.state_store.state)
                self.state_store.state.dirty_flags.clear()
            await asyncio.sleep(config.CSV_DEBOUNCE_SECONDS)

    async def _strategy_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._strategy_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            self._strategy_event.clear()
            try:
                orders = self.router.evaluate(self.state_store.state)
            except Exception as exc:
                logger.warning("strategy evaluation failed: %s", exc)
                continue
            for o in orders:
                try:
                    if config.DRY_RUN:
                        logger.info("DRY_RUN order=%s", o)
                        continue
                    if o.side == "buy":
                        await self.adapter.place_bid(o.symbol, o.price, o.qty)
                    else:
                        await self.adapter.place_ask(o.symbol, o.price, o.qty)
                    logger.info("placed order side=%s symbol=%s px=%s qty=%s reason=%s", o.side, o.symbol, o.price, o.qty, o.reason)
                except Exception as exc:
                    logger.warning("order placement failed for %s: %s", o, exc)

    async def _account_log_loop(self) -> None:
        while True:
            try:
                initial_cash = self.state_store.state.initial_cash or 0.0
                total_pnl = self.state_store.state.server_total_pnl
                if total_pnl is None:
                    total_pnl = self.state_store.state.cash - initial_cash
                logger.info(
                    "account_summary cash=%.2f margin=%.2f pnl_total=%.2f positions=%d",
                    self.state_store.state.cash,
                    self.state_store.state.margin,
                    total_pnl,
                    len(self.state_store.state.positions_raw),
                )
            except Exception as exc:
                logger.warning("account summary log failed: %s", exc)
            await asyncio.sleep(10)

    async def _refresh_external_sources(self) -> None:
        scoreboard = await self.ncaa_source.fetch_scoreboard()
        live_states = self.ncaa_source.refresh_live_games(scoreboard)
        bracket = await self.ncaa_source.fetch_bracket()
        team_states = self.ncaa_source.refresh_bracket_truth(bracket, live_states)
        self.state_store.apply_team_states(team_states)
        probs = await self.playoff_source.refresh()
        self.state_store.apply_probabilities(probs)
        odds_raw_count = 0
        odds_parsed_count = 0
        if self.use_betting_odds:
            raws = await self.live_odds_source.fetch_games_odds()
            odds_raw_count = len(raws)
            live: dict[str, LiveGameProb] = {}
            for raw in raws:
                parsed = self.live_odds_source.extract_moneyline_probs(raw)
                if parsed:
                    live[parsed.game_id] = parsed
            odds_parsed_count = len(live)
            self.state_store.apply_live_game_probs(live)
        else:
            self.state_store.apply_live_game_probs({})
        self._validate_mappings()
        logger.info(
            "external refresh: team_states=%d playoff_probs=%d odds_raw=%d odds_parsed=%d",
            len(team_states),
            len(probs),
            odds_raw_count,
            odds_parsed_count,
        )


    def _validate_mappings(self) -> None:
        state = self.state_store.state
        ncaa_teams = set(state.team_states.keys())
        odds_teams: set[str] = set()
        for game in state.live_game_probs.values():
            odds_teams.add(game.home_team_normalized)
            odds_teams.add(game.away_team_normalized)
        errs = validate_symbol_mapping(state.contracts, state.team_probs, ncaa_teams, odds_teams)
        unresolved = {e.symbol for e in errs if e.reason == "missing_playoffstatus_row"}
        state.unresolved_symbols = unresolved
        for symbol, meta in list(state.contracts.items()):
            blocked = symbol in unresolved
            status = "unresolved" if blocked else "resolved"
            state.contracts[symbol] = ContractMeta(display_symbol=meta.display_symbol, team_name=meta.team_name, normalized_team_name=meta.normalized_team_name, seed=meta.seed, region=meta.region, mapping_status=status, trading_blocked=blocked)


    def _should_poll_live_odds(self, now_ts: float) -> bool:
        if not getattr(self, "use_betting_odds", True):
            return False
        # Poll frequently during live games; otherwise only near scheduled tip-off windows.
        # If NCAA team states are temporarily unavailable, keep polling so odds
        # still flow and dependent strategies/mapping do not stall.
        if not self.state_store.state.team_states:
            return True
        for t in self.state_store.state.team_states.values():
            if t.in_live_game:
                return True
            if t.next_game_start_ts is not None and abs(t.next_game_start_ts - now_ts) <= 60 * 45:
                return True
        return False

    def _recompute_fair_values(self) -> None:
        self.state_store.apply_fair_values(self.fv_engine.recompute_all(self.state_store.state))

    async def _seed_pnl_from_fill_history(self) -> None:
        fills: list[FillView] = []
        try:
            fills = await self.adapter.sync_fills()
        except Exception as exc:
            logger.warning("historical fills sync failed: %s", exc)
        if not fills:
            fills = self._load_local_fills_for_seed()
            if fills:
                logger.info("seeded pnl from local fills.csv rows=%d", len(fills))
        if not fills:
            return

        # Rebuild avg-entry / realized pnl from historical fills so position views
        # do not default to zero-cost for pre-existing inventory.
        state = self.state_store.state
        current_positions = dict(state.positions_raw)
        snapshot_avg = dict(state.avg_entry_by_symbol)
        snapshot_entry_source = dict(state.entry_source_by_symbol)
        state.fills = []
        state.avg_entry_by_symbol.clear()
        state.realized_pnl_by_symbol.clear()
        state.positions_raw = {}
        for fill in fills:
            fill_with_team = FillView(
                timestamp=fill.timestamp,
                order_id=fill.order_id,
                display_symbol=fill.display_symbol,
                team_name=state.contracts.get(fill.display_symbol).team_name if fill.display_symbol in state.contracts else fill.display_symbol,
                price=fill.price,
                traded_qty=fill.traded_qty,
                remaining_qty=fill.remaining_qty,
            )
            state.fills.append(fill_with_team)
            self.pnl_engine.apply_fill(fill_with_team, state)

        # Keep server account positions authoritative after replaying fills.
        state.positions_raw = current_positions
        # If fill history is partial, preserve snapshot averages for symbols that
        # were not reconstructable from fills.
        for symbol, qty in current_positions.items():
            if qty == 0:
                continue
            if symbol not in state.avg_entry_by_symbol and symbol in snapshot_avg:
                state.avg_entry_by_symbol[symbol] = snapshot_avg[symbol]
                state.entry_source_by_symbol[symbol] = snapshot_entry_source.get(symbol, "server_snapshot")

    def _backfill_missing_avg_entries_from_mark(self) -> None:
        """Estimate avg-entry from mark for restart snapshots that only include qty."""
        state = self.state_store.state
        for symbol, qty in state.positions_raw.items():
            if qty == 0 or symbol in state.avg_entry_by_symbol:
                continue
            book = state.order_books.get(symbol)
            fv = state.fair_values.get(symbol)
            mark, _ = self.pnl_engine.compute_mark_price(
                book,
                last_trade=state.last_trade_by_symbol.get(symbol),
                fv=fv.active_fv if fv else None,
            )
            if mark is None or mark <= 0:
                continue
            state.avg_entry_by_symbol[symbol] = mark
            state.entry_source_by_symbol[symbol] = "server_snapshot_mark_backfill"

    def _load_local_fills_for_seed(self) -> list[FillView]:
        path = config.FILLS_CSV
        if not path.exists():
            return []
        fills: list[FillView] = []
        try:
            with path.open("r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = (row.get("display_symbol") or "").strip()
                    if not symbol:
                        continue
                    ts = _safe_float(row.get("timestamp"))
                    oid = _safe_int(row.get("order_id"))
                    px = _safe_float(row.get("price"))
                    qty = _safe_int(row.get("traded_qty"))
                    if ts is None or oid is None or px is None or qty is None:
                        continue
                    fills.append(
                        FillView(
                            timestamp=ts,
                            order_id=oid,
                            display_symbol=symbol,
                            team_name=self.state_store.state.contracts.get(symbol).team_name if symbol in self.state_store.state.contracts else symbol,
                            price=px,
                            traded_qty=qty,
                            remaining_qty=0,
                        )
                    )
        except Exception as exc:
            logger.warning("failed to parse local fills csv for pnl seed: %s", exc)
            return []
        fills.sort(key=lambda x: (x.timestamp, x.order_id))
        return fills


def _safe_float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: str | None) -> int | None:
    try:
        return int(float(value)) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None
