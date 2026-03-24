from __future__ import annotations

import time
from dataclasses import dataclass

from bot import config
from bot.models import BotState


@dataclass(frozen=True)
class RiskDecision:
    ok: bool
    reason: str


class RiskEngine:
    def check_order(self, state: BotState, symbol: str, side: str, price: float, qty: int, reason: str) -> RiskDecision:
        if qty <= 0:
            return RiskDecision(False, "qty<=0")

        current = state.positions_raw.get(symbol, 0)
        projected = current + qty if side == "buy" else current - qty
        if abs(projected) > config.MAX_ABS_POSITION:
            return RiskDecision(False, "position_cap")

        if reason.startswith("live") and abs(projected) > config.LIVE_MAX_POSITION:
            return RiskDecision(False, "live_position_cap")

        # stale data block
        now = time.time()
        if state.source_age("books", now) > config.ACCOUNT_RESYNC_SECONDS * 2:
            return RiskDecision(False, "stale_books")
        if state.source_age("ncaa", now) > config.NCAA_REFRESH_IDLE_SECONDS * 2:
            return RiskDecision(False, "stale_ncaa")
        if reason.startswith("live") and state.source_age("odds", now) > config.ODDS_FRESHNESS_SECONDS:
            return RiskDecision(False, "stale_odds")

        team_fv = state.fair_values.get(symbol)
        if not team_fv:
            return RiskDecision(False, "missing_fv")
        if team_fv.fv_mode == "fixed" and team_fv.fixed_settlement is None:
            return RiskDecision(False, "uncertain_fixed_settlement")

        for o in state.open_orders.values():
            if o.display_symbol != symbol:
                continue
            if side == "buy" and o.side == "sell" and price >= o.price:
                return RiskDecision(False, "self_cross")
            if side == "sell" and o.side == "buy" and price <= o.price:
                return RiskDecision(False, "self_cross")

        mtm = state.cash + sum(state.realized_pnl_by_symbol.values())
        worst_loss = (price * qty) if side == "buy" else ((64 - price) * qty)
        if mtm - worst_loss < -500_000 + config.WORST_CASE_BUFFER:
            return RiskDecision(False, "mtm_threshold_buffer")

        return RiskDecision(True, "ok")
