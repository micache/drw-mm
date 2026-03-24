from __future__ import annotations

import time
from dataclasses import dataclass

from bot.config import BotConfig
from bot.models import BotState


@dataclass(frozen=True)
class RiskDecision:
    ok: bool
    reason: str = ""


def check_order_risk(
    state: BotState,
    config: BotConfig,
    contract_id: str,
    side: str,
    price: float,
    qty: int,
    require_live_odds: bool = False,
) -> RiskDecision:
    if state.account_reduce_only:
        return RiskDecision(False, "account_reduce_only")

    pos = state.positions.get(contract_id)
    current_qty = pos.qty if pos else 0
    projected_qty = current_qty + qty if side == "buy" else current_qty - qty
    if abs(projected_qty) > config.risk.max_abs_position:
        return RiskDecision(False, "position_cap")

    now = time.time()
    last_book = state.ts(f"book:{contract_id}") or 0
    if (now - last_book) > config.strategy.stale_book_seconds:
        return RiskDecision(False, "stale_book")

    last_bracket = state.ts("bracket") or 0
    if (now - last_bracket) > config.strategy.stale_bracket_seconds:
        return RiskDecision(False, "stale_bracket")

    if require_live_odds:
        last_live = state.ts("live_odds") or 0
        if (now - last_live) > config.strategy.stale_live_odds_seconds:
            return RiskDecision(False, "stale_live_odds")

    # Prevent self crossing.
    for order in state.open_orders.values():
        if order.contract_id != contract_id:
            continue
        if side == "buy" and order.side == "sell" and price >= order.price:
            return RiskDecision(False, "self_cross")
        if side == "sell" and order.side == "buy" and price <= order.price:
            return RiskDecision(False, "self_cross")

    server_pnl = state.server_cash if state.server_cash is not None else 0.0
    if side == "buy":
        worst_loss = price * qty * config.risk.adverse_loss_multiplier
    else:
        worst_loss = (64.0 - price) * qty * config.risk.adverse_loss_multiplier

    if server_pnl - worst_loss < -500_000 + config.risk.min_mtm_buffer:
        return RiskDecision(False, "mtm_buffer")

    return RiskDecision(True)
