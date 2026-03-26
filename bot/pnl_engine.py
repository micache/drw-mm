from __future__ import annotations

import time

from bot.models import BotState, FillView, PositionView


class PnlEngine:
    def apply_fill(self, fill: FillView, state: BotState) -> None:
        symbol = fill.display_symbol
        pos = state.positions_raw.get(symbol, 0)
        avg = state.avg_entry_by_symbol.get(symbol, 0.0)
        signed = fill.traded_qty
        state.entry_source_by_symbol[symbol] = "fills_in_memory"

        if pos == 0 or (pos > 0 and signed > 0) or (pos < 0 and signed < 0):
            new_pos = pos + signed
            new_avg = ((avg * abs(pos)) + (fill.price * abs(signed))) / max(1, abs(new_pos))
            state.avg_entry_by_symbol[symbol] = new_avg
            state.positions_raw[symbol] = new_pos
            return

        close_qty = min(abs(pos), abs(signed))
        realized = (fill.price - avg) * close_qty * (1 if pos > 0 else -1)
        state.realized_pnl_by_symbol[symbol] = state.realized_pnl_by_symbol.get(symbol, 0.0) + realized
        new_pos = pos + signed
        state.positions_raw[symbol] = new_pos
        if new_pos == 0:
            state.avg_entry_by_symbol.pop(symbol, None)
        elif (pos > 0 > new_pos) or (pos < 0 < new_pos):
            state.avg_entry_by_symbol[symbol] = fill.price

    @staticmethod
    def compute_mark_price(book, last_trade: float | None = None, fv: float | None = None) -> tuple[float | None, str]:
        if book and book.best_bid and book.best_ask:
            return (book.best_bid.price + book.best_ask.price) / 2.0, "mid"
        if last_trade is not None:
            return last_trade, "last_trade"
        if fv is not None:
            return fv, "fair_value"
        return None, "none"

    def build_position_views(self, state: BotState) -> list[PositionView]:
        now = time.time()
        out: list[PositionView] = []
        for symbol, qty in state.positions_raw.items():
            meta = state.contracts.get(symbol)
            book = state.order_books.get(symbol)
            fv = state.fair_values.get(symbol)
            team_state = state.team_states.get(meta.normalized_team_name) if meta else None
            avg = state.avg_entry_by_symbol.get(symbol)
            entry_source = state.entry_source_by_symbol.get(symbol, "unknown_after_restart")
            mark, mark_source = self.compute_mark_price(book, last_trade=state.last_trade_by_symbol.get(symbol), fv=fv.active_fv if fv else None)
            unrealized = 0.0 if avg is None or mark is None else (mark - avg) * qty
            edges = state.signal_edges_by_symbol.get(symbol, (None, None))
            out.append(
                PositionView(
                    display_symbol=symbol,
                    team_name=meta.team_name if meta else symbol,
                    qty=qty,
                    avg_entry_price=avg,
                    entry_source=entry_source,
                    best_bid=book.best_bid.price if book and book.best_bid else None,
                    best_ask=book.best_ask.price if book and book.best_ask else None,
                    mark_price=mark,
                    mark_price_source=mark_source,
                    fair_value=fv.active_fv if fv else None,
                    fair_value_source_timestamp=fv.source_timestamp if fv else None,
                    settlement_if_known=team_state.fixed_settlement if team_state else None,
                    unrealized_pnl=unrealized,
                    realized_pnl=state.realized_pnl_by_symbol.get(symbol, 0.0),
                    status="alive" if (team_state.alive if team_state else True) else "eliminated",
                    current_round=team_state.current_round if team_state else None,
                    fv_mode=fv.fv_mode if fv else None,
                    mapping_status=meta.mapping_status if meta else "unresolved",
                    ncaa_status_mode=team_state.ncaa_status_mode if team_state else "unresolved",
                    odds_quality_score=(state.live_game_probs.get(team_state.game_id).odds_quality_score if team_state and team_state.game_id and team_state.game_id in state.live_game_probs else None),
                    signal_buy_edge=edges[0],
                    signal_sell_edge=edges[1],
                    last_strategy_reason=state.last_strategy_reason_by_symbol.get(symbol),
                    last_updated_ts=now,
                )
            )
        return out
