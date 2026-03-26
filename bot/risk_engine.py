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
        if symbol in state.unresolved_symbols:
            return RiskDecision(False, "unresolved_symbol_mapping")
        fv = state.fair_values.get(symbol)
        if not fv:
            return RiskDecision(False, "missing_playoffstatus_row")
        if fv.active_fv == 0.0 and fv.fv_mode != "fixed":
            return RiskDecision(False, "missing_playoffstatus_row")

        now = time.time()
        if state.source_age("books", now) > config.ACCOUNT_RESYNC_SECONDS * 3:
            return RiskDecision(False, "inactive_book")
        if state.source_age("ncaa", now) > config.NCAA_BRACKET_REFRESH_SECONDS * 2:
            return RiskDecision(False, "stale_ncaa_state")
        if reason.startswith("live") and state.source_age("odds", now) > config.LIVE_ODDS_FRESHNESS_SECONDS:
            return RiskDecision(False, "stale_odds")
        if reason.startswith("pregame") and state.source_age("odds", now) > config.PREGAME_ODDS_FRESHNESS_SECONDS:
            return RiskDecision(False, "stale_odds")

        current = state.positions_raw.get(symbol, 0)
        signed = qty if side == "buy" else -qty
        projected = current + signed
        reducing = abs(projected) < abs(current)
        if abs(projected) > config.MAX_ABS_POSITION:
            return RiskDecision(False, "position_cap")
        if reason.startswith("live") and abs(projected) > config.LIVE_MAX_POSITION and not reducing:
            return RiskDecision(False, "position_cap")

        if fv.fv_mode == "fixed" and fv.fixed_settlement is None:
            return RiskDecision(False, "fixed_settlement_unconfirmed")

        for o in state.open_orders.values():
            if o.display_symbol != symbol:
                continue
            if side == "buy" and o.side == "sell" and price >= o.price:
                return RiskDecision(False, "self_cross")
            if side == "sell" and o.side == "buy" and price <= o.price:
                return RiskDecision(False, "self_cross")

        mtm = state.cash + sum(state.realized_pnl_by_symbol.values())
        worst_loss = (price * qty) if side == "buy" else ((64 - price) * qty)
        if mtm - worst_loss < -500_000 + config.WORST_CASE_BUFFER and not reducing:
            return RiskDecision(False, "reduce_only")

        return RiskDecision(True, "ok")
