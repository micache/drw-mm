from __future__ import annotations

import time

from bot import config
from bot.models import BotState
from bot.risk_engine import RiskEngine
from bot.strategy_arbitrage import CandidateOrder


class LiveStrategy:
    def __init__(self, risk_engine: RiskEngine) -> None:
        self.risk_engine = risk_engine
        self.last_prob_by_game: dict[str, tuple[float, float]] = {}

    def run(self, state: BotState) -> list[CandidateOrder]:
        out: list[CandidateOrder] = []
        now = time.time()
        for symbol, fv in state.fair_values.items():
            if fv.fv_mode != "live":
                continue
            team = state.contracts.get(symbol)
            if not team:
                continue
            tstate = state.team_states.get(team.normalized_team_name)
            if not tstate or not tstate.game_id:
                continue
            game = state.live_game_probs.get(tstate.game_id)
            if not game or (now - game.source_timestamp) > config.ODDS_FRESHNESS_SECONDS:
                continue

            last_pair = self.last_prob_by_game.get(game.game_id)
            if last_pair:
                if max(abs(game.home_win_prob - last_pair[0]), abs(game.away_win_prob - last_pair[1])) > config.ODDS_JUMP_CIRCUIT_BREAKER:
                    self.last_prob_by_game[game.game_id] = (game.home_win_prob, game.away_win_prob)
                    continue
            self.last_prob_by_game[game.game_id] = (game.home_win_prob, game.away_win_prob)

            book = state.order_books.get(symbol)
            if not book or not book.best_bid or not book.best_ask:
                continue

            if book.best_ask.price <= fv.active_fv - config.LIVE_ENTRY_BUFFER:
                qty = min(5, book.best_ask.qty)
                decision = self.risk_engine.check_order(state, symbol, "buy", book.best_ask.price, qty, "live_dislocation")
                if decision.ok:
                    out.append(CandidateOrder(symbol, "buy", book.best_ask.price, qty, "live_dislocation_buy"))

            if book.best_bid.price >= fv.active_fv + config.LIVE_ENTRY_BUFFER:
                qty = min(5, book.best_bid.qty)
                decision = self.risk_engine.check_order(state, symbol, "sell", book.best_bid.price, qty, "live_dislocation")
                if decision.ok:
                    out.append(CandidateOrder(symbol, "sell", book.best_bid.price, qty, "live_dislocation_sell"))
        return out
