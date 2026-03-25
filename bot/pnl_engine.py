from __future__ import annotations

import time

from bot.models import BotState, FillView, PositionView


class PnlEngine:
    def apply_fill(self, fill: FillView, state: BotState) -> None:
        symbol = fill.display_symbol
        pos = state.positions_raw.get(symbol, 0)
        avg = state.avg_entry_by_symbol.get(symbol, 0.0)
        signed = fill.traded_qty

        if pos == 0 or (pos > 0 and signed > 0) or (pos < 0 and signed < 0):
            new_pos = pos + signed
            new_avg = ((avg * abs(pos)) + (fill.price * abs(signed))) / max(1, abs(new_pos))
            state.avg_entry_by_symbol[symbol] = new_avg
            state.positions_raw[symbol] = new_pos
            return

        # closing logic
        close_qty = min(abs(pos), abs(signed))
        realized = (fill.price - avg) * close_qty * (1 if pos > 0 else -1)
        state.realized_pnl_by_symbol[symbol] = state.realized_pnl_by_symbol.get(symbol, 0.0) + realized
        new_pos = pos + signed
        state.positions_raw[symbol] = new_pos
        if new_pos == 0:
            state.avg_entry_by_symbol[symbol] = 0.0
        elif (pos > 0 > new_pos) or (pos < 0 < new_pos):
            # Position flip: remaining size is a fresh entry at fill price.
            state.avg_entry_by_symbol[symbol] = fill.price

    @staticmethod
    def compute_mark_price(book, last_trade: float | None = None, avg_entry: float | None = None, fv: float | None = None) -> float | None:
        # Competition marking rule: open positions are marked to the last traded price.
        if last_trade is not None:
            return last_trade
        if book and book.best_bid and book.best_ask:
            return (book.best_bid.price + book.best_ask.price) / 2.0
        if book and book.best_bid:
            return book.best_bid.price
        if book and book.best_ask:
            return book.best_ask.price
        return avg_entry if avg_entry is not None else fv

    def build_position_views(self, state: BotState) -> list[PositionView]:
        now = time.time()
        out: list[PositionView] = []
        for symbol, qty in state.positions_raw.items():
            meta = state.contracts.get(symbol)
            book = state.order_books.get(symbol)
            fv = state.fair_values.get(symbol)
            team_state = state.team_states.get(meta.normalized_team_name) if meta else None
            avg = state.avg_entry_by_symbol.get(symbol, 0.0)
            mark = self.compute_mark_price(book, last_trade=state.last_trade_by_symbol.get(symbol), avg_entry=avg, fv=fv.active_fv if fv else None)
            unrealized = ((mark or avg) - avg) * qty
            out.append(
                PositionView(
                    display_symbol=symbol,
                    team_name=meta.team_name if meta else symbol,
                    qty=qty,
                    avg_entry_price=avg,
                    best_bid=book.best_bid.price if book and book.best_bid else None,
                    best_ask=book.best_ask.price if book and book.best_ask else None,
                    mark_price=mark,
                    fair_value=fv.active_fv if fv else None,
                    settlement_if_known=team_state.fixed_settlement if team_state else None,
                    unrealized_pnl=unrealized,
                    realized_pnl=state.realized_pnl_by_symbol.get(symbol, 0.0),
                    status="alive" if (team_state.alive if team_state else True) else "eliminated",
                    current_round=team_state.current_round if team_state else None,
                    last_updated_ts=now,
                )
            )
        return out
