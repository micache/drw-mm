from __future__ import annotations

import time

from bot.models import BotState, TeamFairValue

SETTLEMENT_BY_ROUND = {
    "FIRST_FOUR": 0.0,
    "ROUND_64": 0.0,
    "ROUND_32": 2.0,
    "SWEET_16": 4.0,
    "ELITE_8": 8.0,
    "FINAL_FOUR": 16.0,
    "FINAL": 32.0,
    "CHAMPION": 64.0,
}


class FairValueEngine:
    def recompute_all(self, state: BotState) -> dict[str, TeamFairValue]:
        now = time.time()
        out: dict[str, TeamFairValue] = {}
        for symbol, contract in state.contracts.items():
            norm = contract.normalized_team_name
            team_state = state.team_states.get(norm)
            team_prob = state.team_probs.get(norm)

            fixed = self.compute_fixed_fv(team_state)
            baseline = self.compute_baseline_fv(team_prob)
            live_fv = self.compute_live_fv(team_state, team_prob, state.live_game_probs)

            if fixed is not None:
                active = fixed
                mode = "fixed"
            elif live_fv is not None:
                active = live_fv
                mode = "live"
            else:
                active = baseline
                mode = "baseline"

            out[symbol] = TeamFairValue(
                display_symbol=symbol,
                team_name=contract.team_name,
                baseline_fv=baseline,
                live_fv=live_fv,
                active_fv=active,
                fixed_settlement=fixed,
                fv_mode=mode,
                source_timestamp=now,
            )
        return out

    @staticmethod
    def compute_fixed_fv(team_state) -> float | None:
        if not team_state:
            return None
        return team_state.fixed_settlement

    @staticmethod
    def compute_baseline_fv(team_prob) -> float:
        return team_prob.baseline_fv if team_prob else 0.0

    def compute_live_fv(self, team_state, team_prob, live_probs) -> float | None:
        if not team_state or not team_prob or not team_state.in_live_game or not team_state.game_id:
            return None
        game = live_probs.get(team_state.game_id)
        if not game:
            return None

        if team_state.normalized_team_name == game.home_team_normalized:
            p_live = game.home_win_prob
        elif team_state.normalized_team_name == game.away_team_normalized:
            p_live = game.away_win_prob
        else:
            return None

        lose_settlement = SETTLEMENT_BY_ROUND.get(team_state.current_round or "ROUND_64", 0.0)
        ev_if_win_now = self._ev_if_win_current_game(team_state, team_prob)
        return (p_live * ev_if_win_now) + ((1 - p_live) * lose_settlement)

    @staticmethod
    def _ev_if_win_current_game(team_state, team_prob) -> float:
        if not team_state or not team_prob:
            return 0.0
        survive = max(1e-6, {
            "ROUND_32": team_prob.p_s16,
            "SWEET_16": team_prob.p_e8,
            "ELITE_8": team_prob.p_f4,
            "FINAL_FOUR": team_prob.p_final,
            "FINAL": team_prob.p_champion,
        }.get(team_state.current_round or "ROUND_32", team_prob.p_s16))

        cond_p_e8 = min(1.0, team_prob.p_e8 / survive)
        cond_p_f4 = min(1.0, team_prob.p_f4 / survive)
        cond_p_final = min(1.0, team_prob.p_final / survive)
        cond_p_champ = min(1.0, team_prob.p_champion / survive)

        return (
            64 * cond_p_champ
            + 32 * (cond_p_final - cond_p_champ)
            + 16 * (cond_p_f4 - cond_p_final)
            + 8 * (cond_p_e8 - cond_p_f4)
        )
