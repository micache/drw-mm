from __future__ import annotations

import csv
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from bot.models import BotState


def _atomic_write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), newline="") as tmp:
        writer = csv.writer(tmp)
        writer.writerow(headers)
        writer.writerows(rows)
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def write_positions(state: BotState, path: Path) -> None:
    rows: list[list[object]] = []
    now = time.time()
    for contract_id, position in state.positions.items():
        book = state.books.get(contract_id)
        fv = state.fair_values.get(contract_id)
        bracket = state.bracket_states.get(state.contracts.get(contract_id).normalized_team_name) if contract_id in state.contracts else None
        best_bid = book.best_bid.price if book and book.best_bid else ""
        best_ask = book.best_ask.price if book and book.best_ask else ""
        mark = best_bid if position.qty < 0 else best_ask
        mark = mark if mark != "" else fv.value if fv else 0.0
        unrealized = (mark - position.avg_entry_price) * position.qty if isinstance(mark, (int, float)) else 0.0
        rows.append([
            now,
            contract_id,
            state.contracts[contract_id].team_name if contract_id in state.contracts else contract_id,
            position.qty,
            position.avg_entry_price,
            best_bid,
            best_ask,
            mark,
            fv.value if fv else "",
            bracket.settlement_if_known if bracket else "",
            unrealized,
            "",
            "server" if state.server_cash is not None else "local",
            bracket.current_round if bracket else "",
            bracket.status if bracket else "unknown",
        ])

    _atomic_write_csv(
        path,
        [
            "timestamp",
            "contract_id",
            "team_name",
            "qty",
            "avg_entry_price",
            "best_bid",
            "best_ask",
            "mark_price",
            "fair_value",
            "settlement_if_known",
            "unrealized_pnl",
            "realized_pnl",
            "pnl_source",
            "current_round",
            "status",
        ],
        rows,
    )


def write_open_orders(state: BotState, path: Path) -> None:
    rows = [[o.order_id, o.contract_id, o.side, o.price, o.qty] for o in state.open_orders.values()]
    _atomic_write_csv(path, ["order_id", "contract_id", "side", "price", "qty"], rows)


def append_fills(state: BotState, path: Path, from_index: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["timestamp", "order_id", "contract_id", "price", "qty"])
        for fill in state.fills[from_index:]:
            writer.writerow([_format_timestamp(fill.timestamp), fill.order_id, fill.contract_id, fill.price, fill.qty])
    return len(state.fills)


def write_fair_values(state: BotState, path: Path) -> None:
    rows = [[cid, fv.value, fv.source] for cid, fv in state.fair_values.items()]
    _atomic_write_csv(path, ["contract_id", "fair_value", "source"], rows)


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
