from __future__ import annotations

from bot.models import BotState
from bot.strategy_arbitrage import ArbitrageStrategy, CandidateOrder
from bot.strategy_live import LiveStrategy


class StrategyRouter:
    def __init__(self, arb: ArbitrageStrategy, live: LiveStrategy) -> None:
        self.arb = arb
        self.live = live

    def evaluate(self, state: BotState) -> list[CandidateOrder]:
        out: list[CandidateOrder] = []
        out.extend(self.arb.eliminated_mispricing(state))
        out.extend(self.arb.basket_arbitrage(state))
        out.extend(self.live.run(state))
        return out
