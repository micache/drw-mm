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
NEXT_SURVIVAL_ATTR = {
    "ROUND_64": "p_r32",
    "ROUND_32": "p_s16",
    "SWEET_16": "p_e8",
    "ELITE_8": "p_f4",
    "FINAL_FOUR": "p_final",
    "FINAL": "p_champion",
}


class FairValueEngine:
    def recompute_all(self, state: BotState) -> dict[str, TeamFairValue]:
        now = time.time()
        out: dict[str, TeamFairValue] = {}
        for symbol, contract in state.contracts.items():
            if contract.trading_blocked:
                state.unresolved_symbols.add(symbol)
            norm = contract.normalized_team_name
            team_state = state.team_states.get(norm)
            team_prob = state.team_probs.get(norm)

            fixed = self.compute_fixed_fv(team_state)
            baseline = self.compute_baseline_fv(team_prob)
            live_prob, pregame_prob = self._extract_probabilities(team_state, state.live_game_probs)
            live_fv = self.compute_active_fv(team_state, team_prob, live_prob)
            pregame_fv = self.compute_active_fv(team_state, team_prob, pregame_prob)

            mode = "baseline"
            active = baseline
            if fixed is not None:
                mode = "fixed"
                active = fixed
            elif live_fv is not None:
                mode = "live"
                active = live_fv
            elif pregame_fv is not None:
                mode = "pregame"
                active = pregame_fv

            if team_state and team_state.alive and team_prob and active == 0.0 and fixed is None:
                state.unresolved_symbols.add(symbol)
                mode = "blocked_zero_fv"

            out[symbol] = TeamFairValue(
                display_symbol=symbol,
                team_name=contract.team_name,
                baseline_fv=baseline,
                live_fv=live_fv,
                pregame_fv=pregame_fv,
                active_fv=active,
                fixed_settlement=fixed,
                fv_mode=mode,
                source_timestamp=now,
            )
        return out

    @staticmethod
    def compute_baseline_fv(team_prob) -> float:
        return team_prob.baseline_fv if team_prob else 0.0

    @staticmethod
    def compute_fixed_fv(team_state) -> float | None:
        return team_state.fixed_settlement if team_state and team_state.fixed_settlement is not None else None

    def compute_conditioned_fv(self, team_prob, current_round: str | None, p_win_next: float) -> float | None:
        if not team_prob or not current_round:
            return None
        survive_attr = NEXT_SURVIVAL_ATTR.get(current_round)
        if not survive_attr:
            return None
        survive_prob = max(1e-6, float(getattr(team_prob, survive_attr, 0.0)))
        settle_lose = SETTLEMENT_BY_ROUND.get(current_round, 0.0)

        cond_p_s16 = min(1.0, team_prob.p_s16 / survive_prob)
        cond_p_e8 = min(1.0, team_prob.p_e8 / survive_prob)
        cond_p_f4 = min(1.0, team_prob.p_f4 / survive_prob)
        cond_p_final = min(1.0, team_prob.p_final / survive_prob)
        cond_p_champ = min(1.0, team_prob.p_champion / survive_prob)
        ev_if_win = (
            64 * cond_p_champ
            + 32 * (cond_p_final - cond_p_champ)
            + 16 * (cond_p_f4 - cond_p_final)
            + 8 * (cond_p_e8 - cond_p_f4)
            + 4 * max(0.0, cond_p_s16 - cond_p_e8)
            + 2 * max(0.0, 1.0 - cond_p_s16)
        )
        p = max(0.0, min(1.0, p_win_next))
        return (p * ev_if_win) + ((1.0 - p) * settle_lose)

    def compute_active_fv(self, team_state, team_prob, live_or_pregame_prob: float | None) -> float | None:
        if not team_state or not team_prob or live_or_pregame_prob is None:
            return None
        return self.compute_conditioned_fv(team_prob, team_state.current_round, live_or_pregame_prob)

    @staticmethod
    def _extract_probabilities(team_state, live_probs) -> tuple[float | None, float | None]:
        if not team_state:
            return None, None
        game = _resolve_game_for_team(team_state, live_probs)
        if not game:
            return None, None
        if team_state.normalized_team_name == game.home_team_normalized:
            p = game.home_win_prob
        elif team_state.normalized_team_name == game.away_team_normalized:
            p = game.away_win_prob
        else:
            return None, None
        if team_state.in_live_game:
            return p, None
        if team_state.has_upcoming_game:
            return None, p
        return None, None


def _resolve_game_for_team(team_state, live_probs):
    # Prefer explicit NCAA game id when an exact key exists, but fall back to
    # team-name matching because Odds API event ids are different ids.
    if team_state.game_id and team_state.game_id in live_probs:
        return live_probs[team_state.game_id]
    matches = [
        game
        for game in live_probs.values()
        if team_state.normalized_team_name in (game.home_team_normalized, game.away_team_normalized)
    ]
    if not matches:
        return None
    matches.sort(key=lambda g: (g.source_timestamp, g.bookmakers_used), reverse=True)
    return matches[0]
