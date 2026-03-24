from __future__ import annotations

from dataclasses import dataclass

from bot import config
from bot.models import BotState
from bot.risk_engine import RiskEngine


@dataclass(frozen=True)
class CandidateOrder:
    symbol: str
    side: str
    price: float
    qty: int
    reason: str


class ArbitrageStrategy:
    def __init__(self, risk_engine: RiskEngine) -> None:
        self.risk_engine = risk_engine

    def eliminated_mispricing(self, state: BotState) -> list[CandidateOrder]:
        out: list[CandidateOrder] = []
        for symbol, fv in state.fair_values.items():
            if fv.fv_mode != "fixed" or fv.fixed_settlement is None:
                continue
            book = state.order_books.get(symbol)
            if not book:
                continue
            best_bid = book.best_bid
            best_ask = book.best_ask
            s = fv.fixed_settlement

            if best_ask and (s - best_ask.price) >= config.ELIMINATED_MIN_EDGE:
                qty = min(10, best_ask.qty, config.MAX_ABS_POSITION - abs(state.positions_raw.get(symbol, 0)))
                if qty > 0:
                    decision = self.risk_engine.check_order(state, symbol, "buy", best_ask.price, qty, "eliminated")
                    if decision.ok:
                        out.append(CandidateOrder(symbol, "buy", best_ask.price, qty, "eliminated_mispricing_buy"))

            if best_bid and (best_bid.price - s) >= config.ELIMINATED_MIN_EDGE:
                qty = min(10, best_bid.qty, config.MAX_ABS_POSITION - abs(state.positions_raw.get(symbol, 0)))
                if qty > 0:
                    decision = self.risk_engine.check_order(state, symbol, "sell", best_bid.price, qty, "eliminated")
                    if decision.ok:
                        out.append(CandidateOrder(symbol, "sell", best_bid.price, qty, "eliminated_mispricing_sell"))
        return out

    def basket_arbitrage(self, state: BotState) -> list[CandidateOrder]:
        if len(state.contracts) != 68:
            return []
        qty = 1
        long_total = 0.0
        short_total = 0.0
        long_orders: list[CandidateOrder] = []
        short_orders: list[CandidateOrder] = []

        for symbol in state.contracts:
            book = state.order_books.get(symbol)
            if not book or not book.best_ask or not book.best_bid:
                return []
            if book.best_ask.qty < qty or book.best_bid.qty < qty:
                return []
            long_total += book.best_ask.price
            short_total += book.best_bid.price
            long_orders.append(CandidateOrder(symbol, "buy", book.best_ask.price, qty, "basket_long"))
            short_orders.append(CandidateOrder(symbol, "sell", book.best_bid.price, qty, "basket_short"))

        if (224.0 - long_total) >= config.BASKET_MIN_EDGE:
            return [o for o in long_orders if self.risk_engine.check_order(state, o.symbol, o.side, o.price, o.qty, o.reason).ok]
        if (short_total - 224.0) >= config.BASKET_MIN_EDGE:
            return [o for o in short_orders if self.risk_engine.check_order(state, o.symbol, o.side, o.price, o.qty, o.reason).ok]
        return []
