from __future__ import annotations

from bot.models import BotState
from bot.strategy_arbitrage import ArbitrageStrategy, CandidateOrder
from bot.strategy_live import LiveStrategy
from bot.strategy_pregame import PregameStrategy
from bot.inventory_reduction import InventoryReductionStrategy


class StrategyRouter:
    def __init__(self, arb: ArbitrageStrategy, pregame: PregameStrategy, live: LiveStrategy, inventory_reduction: InventoryReductionStrategy) -> None:
        self.arb = arb
        self.pregame = pregame
        self.live = live
        self.inventory_reduction = inventory_reduction

    def evaluate(self, state: BotState) -> list[CandidateOrder]:
        out: list[CandidateOrder] = []
        out.extend(self.arb.eliminated_mispricing(state))
        out.extend(self.arb.basket_arbitrage(state))
        out.extend(self.pregame.run(state))
        out.extend(self.live.run(state))
        out.extend(self.inventory_reduction.run(state))
        for order in out:
            state.last_strategy_reason_by_symbol[order.symbol] = order.reason
        return out
