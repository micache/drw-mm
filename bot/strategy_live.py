from __future__ import annotations

import time

from bot import config
from bot.models import BotState
from bot.risk_engine import RiskEngine
from bot.strategy_arbitrage import CandidateOrder


class LiveStrategy:
    def __init__(self, risk_engine: RiskEngine) -> None:
        self.risk_engine = risk_engine
        self.last_prob_by_game: dict[str, float] = {}
        self.pending_jump: set[str] = set()

    def run(self, state: BotState) -> list[CandidateOrder]:
        out: list[CandidateOrder] = []
        now = time.time()
        for symbol, fv in state.fair_values.items():
            if fv.fv_mode != "live":
                continue
            contract = state.contracts.get(symbol)
            if not contract or contract.trading_blocked:
                continue
            tstate = state.team_states.get(contract.normalized_team_name)
            if not tstate or not tstate.game_id:
                continue
            game = state.live_game_probs.get(tstate.game_id)
            if not game or (now - game.source_timestamp) > config.LIVE_ODDS_FRESHNESS_SECONDS:
                continue
            current = game.home_win_prob if contract.normalized_team_name == game.home_team_normalized else game.away_win_prob
            last = self.last_prob_by_game.get(game.game_id)
            jump_block = False
            if last is not None and abs(current - last) >= config.LIVE_CONFIRMATION_DELTA:
                if game.game_id in self.pending_jump:
                    self.pending_jump.remove(game.game_id)
                else:
                    self.pending_jump.add(game.game_id)
                    jump_block = True
            self.last_prob_by_game[game.game_id] = current

            book = state.order_books.get(symbol)
            if not book:
                continue
            pos = state.positions_raw.get(symbol, 0)

            buy_edge = (fv.active_fv - book.best_ask.price) if book.best_ask else None
            sell_edge = (book.best_bid.price - fv.active_fv) if book.best_bid else None
            state.signal_edges_by_symbol[symbol] = (buy_edge, sell_edge)

            if book.best_ask and buy_edge is not None and buy_edge >= config.LIVE_TAKE_BUFFER:
                emergency = buy_edge >= config.LIVE_EMERGENCY_TAKE_BUFFER
                if (not jump_block or emergency) and self.risk_engine.check_order(state, symbol, "buy", book.best_ask.price, min(5, book.best_ask.qty), "live_dislocation").ok:
                    out.append(CandidateOrder(symbol, "buy", book.best_ask.price, min(5, book.best_ask.qty), "live_dislocation_buy"))

            if book.best_bid and sell_edge is not None and sell_edge >= config.LIVE_TAKE_BUFFER:
                emergency = sell_edge >= config.LIVE_EMERGENCY_TAKE_BUFFER
                if (not jump_block or emergency) and self.risk_engine.check_order(state, symbol, "sell", book.best_bid.price, min(5, book.best_bid.qty), "live_dislocation").ok:
                    out.append(CandidateOrder(symbol, "sell", book.best_bid.price, min(5, book.best_bid.qty), "live_dislocation_sell"))

            if pos < 0 and book.best_ask and book.best_ask.price <= fv.active_fv - config.LIVE_COVER_BUFFER:
                qty = min(abs(pos), book.best_ask.qty, 5)
                if self.risk_engine.check_order(state, symbol, "buy", book.best_ask.price, qty, "live_reduce").ok:
                    out.append(CandidateOrder(symbol, "buy", book.best_ask.price, qty, "live_cover_buy"))
            if pos > 0 and book.best_bid and book.best_bid.price >= fv.active_fv + config.LIVE_REDUCE_BUFFER:
                qty = min(abs(pos), book.best_bid.qty, 5)
                if self.risk_engine.check_order(state, symbol, "sell", book.best_bid.price, qty, "live_reduce").ok:
                    out.append(CandidateOrder(symbol, "sell", book.best_bid.price, qty, "live_reduce_sell"))
        return out
