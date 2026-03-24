from __future__ import annotations

import time
from dataclasses import replace

from bot.models import (
    BotState,
    BracketState,
    FairValue,
    Fill,
    OpenOrder,
    OrderBook,
    Position,
)


def apply_book_update(state: BotState, book: OrderBook) -> None:
    state.books[book.contract_id] = book
    state.touch(f"book:{book.contract_id}", time.time())


def apply_position_snapshot(state: BotState, positions: dict[str, int]) -> None:
    new_positions: dict[str, Position] = {}
    for contract_id, qty in positions.items():
        previous = state.positions.get(contract_id)
        new_positions[contract_id] = Position(
            contract_id=contract_id,
            qty=qty,
            avg_entry_price=previous.avg_entry_price if previous else 0.0,
        )
    state.positions = new_positions
    state.touch("positions", time.time())


def apply_order_event(state: BotState, order: OpenOrder) -> None:
    if order.qty == 0:
        state.open_orders.pop(order.order_id, None)
    else:
        state.open_orders[order.order_id] = order
    state.touch("orders", time.time())


def apply_fill_event(state: BotState, fill: Fill) -> None:
    state.fills.append(fill)
    pos = state.positions.get(fill.contract_id, Position(contract_id=fill.contract_id, qty=0, avg_entry_price=0.0))
    signed_qty = fill.qty
    new_qty = pos.qty + signed_qty
    if new_qty == 0:
        avg = 0.0
    elif pos.qty == 0:
        avg = fill.price
    else:
        avg = ((pos.avg_entry_price * pos.qty) + (fill.price * signed_qty)) / new_qty
    state.positions[fill.contract_id] = replace(pos, qty=new_qty, avg_entry_price=avg)
    state.touch("fills", time.time())


def apply_fv_update(state: BotState, fv: FairValue) -> None:
    state.fair_values[fv.contract_id] = fv
    state.touch(f"fv:{fv.contract_id}", time.time())


def apply_bracket_update(state: BotState, bracket_state: BracketState) -> None:
    state.bracket_states[bracket_state.normalized_team_name] = bracket_state
    state.touch("bracket", time.time())
