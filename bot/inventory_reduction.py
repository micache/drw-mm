from __future__ import annotations

from bot import config
from bot.models import BotState
from bot.risk_engine import RiskEngine
from bot.strategy_arbitrage import CandidateOrder


class InventoryReductionStrategy:
    def __init__(self, risk_engine: RiskEngine) -> None:
        self.risk_engine = risk_engine

    def run(self, state: BotState) -> list[CandidateOrder]:
        out: list[CandidateOrder] = []
        for symbol, pos in state.positions_raw.items():
            if pos == 0:
                continue
            fv = state.fair_values.get(symbol)
            book = state.order_books.get(symbol)
            if not fv or not book:
                continue
            if pos < 0 and book.best_ask and book.best_ask.price <= fv.active_fv - config.COVER_BUFFER:
                qty = min(abs(pos), book.best_ask.qty, 5)
                if qty > 0 and self.risk_engine.check_order(state, symbol, "buy", book.best_ask.price, qty, "inventory_reduction").ok:
                    out.append(CandidateOrder(symbol, "buy", book.best_ask.price, qty, "inventory_cover_buy"))
            if pos > 0 and book.best_bid and book.best_bid.price >= fv.active_fv + config.REDUCE_BUFFER:
                qty = min(abs(pos), book.best_bid.qty, 5)
                if qty > 0 and self.risk_engine.check_order(state, symbol, "sell", book.best_bid.price, qty, "inventory_reduction").ok:
                    out.append(CandidateOrder(symbol, "sell", book.best_bid.price, qty, "inventory_reduce_sell"))
        return out
