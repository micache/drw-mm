from __future__ import annotations

import time

from bot import config
from bot.models import BotState
from bot.risk_engine import RiskEngine
from bot.strategy_arbitrage import CandidateOrder


class PregameStrategy:
    def __init__(self, risk_engine: RiskEngine) -> None:
        self.risk_engine = risk_engine

    def run(self, state: BotState) -> list[CandidateOrder]:
        if not config.ENABLE_PREGAME_STRATEGY:
            return []
        out: list[CandidateOrder] = []
        now = time.time()
        for symbol, fv in state.fair_values.items():
            if fv.fv_mode != "pregame":
                continue
            contract = state.contracts.get(symbol)
            if not contract or contract.trading_blocked:
                continue
            tstate = state.team_states.get(contract.normalized_team_name)
            if not tstate or tstate.ncaa_status_mode != "upcoming":
                continue
            if state.source_age("odds", now) > config.PREGAME_ODDS_FRESHNESS_SECONDS:
                continue
            if not tstate.game_id or tstate.game_id not in state.live_game_probs:
                continue
            game = state.live_game_probs[tstate.game_id]
            if game.bookmakers_used < config.PREGAME_MIN_BOOKMAKERS:
                continue

            book = state.order_books.get(symbol)
            if not book:
                continue
            pos = state.positions_raw.get(symbol, 0)
            if book.best_ask and (fv.active_fv - book.best_ask.price) >= config.PREGAME_TAKE_BUFFER:
                qty = min(book.best_ask.qty, max(0, config.PREGAME_MAX_POSITION - abs(pos)), 5)
                if qty > 0:
                    if self.risk_engine.check_order(state, symbol, "buy", book.best_ask.price, qty, "pregame_dislocation").ok:
                        out.append(CandidateOrder(symbol, "buy", book.best_ask.price, qty, "pregame_dislocation_buy"))
            if book.best_bid and (book.best_bid.price - fv.active_fv) >= config.PREGAME_TAKE_BUFFER:
                qty = min(book.best_bid.qty, max(0, config.PREGAME_MAX_POSITION - abs(pos)), 5)
                if qty > 0:
                    if self.risk_engine.check_order(state, symbol, "sell", book.best_bid.price, qty, "pregame_dislocation").ok:
                        out.append(CandidateOrder(symbol, "sell", book.best_bid.price, qty, "pregame_dislocation_sell"))
        return out
