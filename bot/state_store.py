from __future__ import annotations

import time

from bot.models import BotState, FillView, LiveGameProb, OrderBook, OrderView, TeamFairValue, TeamProbabilities, TeamTournamentState


class StateStore:
    def __init__(self) -> None:
        self.state = BotState()

    def apply_account_snapshot(
        self,
        cash: float,
        margin: float,
        positions: dict[str, int],
        total_pnl: float | None = None,
        avg_entries: dict[str, float] | None = None,
    ) -> None:
        self.state.cash = cash
        self.state.margin = margin
        if self.state.initial_cash is None:
            self.state.initial_cash = cash
        self.state.server_total_pnl = total_pnl
        self.state.positions_raw = {k: v for k, v in positions.items() if v != 0}
        if avg_entries:
            for symbol, avg in avg_entries.items():
                if symbol in self.state.positions_raw:
                    self.state.avg_entry_by_symbol[symbol] = avg
                    self.state.entry_source_by_symbol[symbol] = "server_snapshot"
        for symbol in self.state.positions_raw:
            self.state.entry_source_by_symbol.setdefault(symbol, "server_snapshot_qty_only")
        self.state.mark_dirty("account")
        self.state.set_source_timestamp("account", time.time())

    def apply_open_orders_snapshot(self, open_orders: dict[int, OrderView]) -> None:
        self.state.open_orders = open_orders
        self.state.mark_dirty("orders")
        self.state.set_source_timestamp("orders", time.time())

    def apply_orderbook_snapshot(self, order_books: dict[str, OrderBook]) -> None:
        self.state.order_books = order_books
        self.state.mark_dirty("books")
        self.state.set_source_timestamp("books", time.time())

    def apply_orderbook_delta(self, order_books: dict[str, OrderBook]) -> None:
        self.state.order_books.update(order_books)
        self.state.mark_dirty("books")
        self.state.set_source_timestamp("books", time.time())

    def apply_order_update(self, order: OrderView) -> None:
        if order.canceled or order.qty_abs == 0:
            self.state.open_orders.pop(order.order_id, None)
        else:
            self.state.open_orders[order.order_id] = order
        self.state.mark_dirty("orders")

    def apply_fill(self, fill: FillView) -> None:
        self.state.fills.append(fill)
        self.state.mark_dirty("fills")

    def apply_trade(self, display_symbol: str, price: float) -> None:
        self.state.last_trade_by_symbol[display_symbol] = price
        self.state.mark_dirty("trades")
        self.state.set_source_timestamp("trades", time.time())

    def apply_team_states(self, team_states: dict[str, TeamTournamentState]) -> None:
        self.state.team_states = team_states
        self.state.mark_dirty("team_states")
        self.state.set_source_timestamp("ncaa", time.time())

    def apply_probabilities(self, team_probs: dict[str, TeamProbabilities]) -> None:
        self.state.team_probs = team_probs
        self.state.mark_dirty("team_probs")
        self.state.set_source_timestamp("playoffstatus", time.time())

    def apply_live_game_probs(self, live_probs: dict[str, LiveGameProb]) -> None:
        self.state.live_game_probs = live_probs
        self.state.mark_dirty("live_probs")
        self.state.set_source_timestamp("odds", time.time())

    def apply_fair_values(self, fair_values: dict[str, TeamFairValue]) -> None:
        self.state.fair_values = fair_values
        self.state.mark_dirty("fair_values")
        self.state.set_source_timestamp("fair_values", time.time())
