from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

from bot import config
from bot.models import BotState, FillView, OrderView
from bot.pnl_engine import PnlEngine


class Reporter:
    def __init__(self) -> None:
        self.last_fill_keys: set[tuple[float, int, str, float, int]] = set()
        self.pnl_engine = PnlEngine()

    def write_all(self, state: BotState) -> None:
        positions = self.pnl_engine.build_position_views(state)
        self._write_positions(positions)
        self._write_orders(state.open_orders)
        self._append_fills(state.fills)
        self._write_fair_values(state)

    def _write_positions(self, positions) -> None:
        rows = []
        for p in positions:
            rows.append([
                p.display_symbol,
                p.team_name,
                p.qty,
                p.avg_entry_price,
                p.entry_source,
                p.best_bid,
                p.best_ask,
                p.mark_price,
                p.fair_value,
                p.last_strategy_reason,
                p.unrealized_pnl,
            ])
        self._atomic_csv(
            config.POSITIONS_CSV,
            [
                "display_symbol",
                "team_name",
                "qty",
                "avg_entry_price_est",
                "entry_source",
                "best_bid",
                "best_ask",
                "mark_price",
                "fair_value",
                "last_strategy_reason",
                "unrealized_pnl",
            ],
            rows,
        )

    def _write_orders(self, orders: dict[int, OrderView]) -> None:
        rows = [[o.order_id, o.display_symbol, o.team_name, o.side, o.price, o.qty_signed, o.qty_abs] for o in orders.values()]
        self._atomic_csv(config.ORDERS_CSV, ["order_id", "display_symbol", "team_name", "side", "price", "qty_signed", "qty_abs"], rows)

    def _append_fills(self, fills: list[FillView]) -> None:
        path = config.FILLS_CSV
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        with path.open("a", newline="") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["timestamp", "order_id", "display_symbol", "price", "traded_qty"])
            for fill in fills:
                key = (fill.timestamp, fill.order_id, fill.display_symbol, fill.price, fill.traded_qty)
                if key in self.last_fill_keys:
                    continue
                self.last_fill_keys.add(key)
                writer.writerow([fill.timestamp, fill.order_id, fill.display_symbol, fill.price, fill.traded_qty])

    def _write_fair_values(self, state: BotState) -> None:
        rows = [[x.display_symbol, x.team_name, x.active_fv] for x in state.fair_values.values()]
        self._atomic_csv(config.FAIR_VALUES_CSV, ["display_symbol", "team_name", "fair_value"], rows)

    @staticmethod
    def _atomic_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", newline="", delete=False, dir=path.parent) as tmp:
            writer = csv.writer(tmp)
            writer.writerow(headers)
            writer.writerows(rows)
            tmp_path = tmp.name
        os.replace(tmp_path, path)
