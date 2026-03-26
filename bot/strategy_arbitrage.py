from __future__ import annotations

import time
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
        now = time.time()
        for symbol, fv in state.fair_values.items():
            contract = state.contracts.get(symbol)
            if not contract or contract.trading_blocked:
                continue
            tstate = state.team_states.get(contract.normalized_team_name)
            if not tstate:
                continue
            if fv.fv_mode != "fixed" or fv.fixed_settlement is None or tstate.ncaa_status_mode != "eliminated_fixed":
                continue
            book = state.order_books.get(symbol)
            if not book or (book.timestamp and now - book.timestamp > 10):
                continue
            s = fv.fixed_settlement
            if book.best_ask and (s - book.best_ask.price) >= config.ELIMINATED_MIN_EDGE:
                qty = min(10, book.best_ask.qty)
                if qty > 0 and self.risk_engine.check_order(state, symbol, "buy", book.best_ask.price, qty, "eliminated").ok:
                    out.append(CandidateOrder(symbol, "buy", book.best_ask.price, qty, "eliminated_buy_misprice"))
            if book.best_bid and (book.best_bid.price - s) >= config.ELIMINATED_MIN_EDGE:
                qty = min(10, book.best_bid.qty)
                if qty > 0 and self.risk_engine.check_order(state, symbol, "sell", book.best_bid.price, qty, "eliminated").ok:
                    out.append(CandidateOrder(symbol, "sell", book.best_bid.price, qty, "eliminated_sell_misprice"))
        return out

    def basket_arbitrage(self, state: BotState) -> list[CandidateOrder]:
        if not config.ENABLE_BASKET_ARBITRAGE:
            return []
        if len(state.contracts) != 68:
            return []
        if any(s in state.unresolved_symbols for s in state.contracts):
            return []
        qty = 1
        long_total = 0.0
        short_total = 0.0
        long_orders: list[CandidateOrder] = []
        short_orders: list[CandidateOrder] = []
        now = time.time()
        for symbol, contract in state.contracts.items():
            if contract.trading_blocked:
                return []
            book = state.order_books.get(symbol)
            if not book or not book.best_ask or not book.best_bid:
                return []
            if book.timestamp and now - book.timestamp > 10:
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
