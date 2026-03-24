from __future__ import annotations

import time

from bot.models import BotState, FairValue
from bot.normalize import normalize_team_name
from bot.probability_source import baseline_ev_from_probs


def recompute_fair_values(state: BotState) -> list[FairValue]:
    out: list[FairValue] = []
    now = time.time()
    for contract_id, contract in state.contracts.items():
        norm = contract.normalized_team_name
        bracket = state.bracket_states.get(norm)
        if bracket and bracket.status == "eliminated" and bracket.settlement_if_known is not None:
            out.append(FairValue(contract_id=contract_id, value=bracket.settlement_if_known, source="official_bracket", updated_at=now))
            continue

        base_probs = state.baseline_probs.get(norm, {})
        baseline_ev = baseline_ev_from_probs(base_probs)

        game = state.live_games.get(norm)
        if not game:
            out.append(FairValue(contract_id=contract_id, value=baseline_ev, source="baseline", updated_at=now))
            continue

        if normalize_team_name(game.team_a) == norm:
            p_live = game.p_team_a
        else:
            p_live = game.p_team_b

        lose_settlement = bracket.settlement_if_known if bracket and bracket.settlement_if_known is not None else 0.0
        ev_if_win_now = min(64.0, max(0.0, baseline_ev + 2.0))
        live_ev = (p_live * ev_if_win_now) + ((1 - p_live) * lose_settlement)
        out.append(FairValue(contract_id=contract_id, value=min(64.0, max(0.0, live_ev)), source="live_conditioned", updated_at=now))

    return out
