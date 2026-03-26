from __future__ import annotations

import datetime as dt
import time
from typing import Any

import aiohttp

from bot.models import TeamTournamentState
from bot.team_mapping import TeamMapper

SETTLEMENT_BY_LOSS_ROUND = {
    "FIRST_FOUR": 0.0,
    "ROUND_64": 0.0,
    "ROUND_32": 2.0,
    "SWEET_16": 4.0,
    "ELITE_8": 8.0,
    "FINAL_FOUR": 16.0,
    "FINAL": 32.0,
}


class NcaaSource:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, mapper: TeamMapper) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.mapper = mapper

    async def fetch_scoreboard(self, date_or_path: str | None = None) -> list[dict[str, Any]]:
        date_or_path = date_or_path or dt.date.today().isoformat()
        url = f"{self.base_url}/scoreboard/basketball-men/d1/{date_or_path}"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status >= 400:
                    return []
                payload = await resp.json()
            return payload if isinstance(payload, list) else payload.get("games", [])
        except Exception:
            return []

    async def fetch_bracket(self) -> dict[str, Any]:
        url = f"{self.base_url}/bracket/basketball-men/d1/2026"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status >= 400:
                    return {}
                data = await resp.json()
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    async def fetch_game(self, game_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/game/{game_id}"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status >= 400:
                    return {}
                return await resp.json()
        except Exception:
            return {}

    def refresh_live_games(self, scoreboard: list[dict[str, Any]]) -> dict[str, TeamTournamentState]:
        now = time.time()
        out: dict[str, TeamTournamentState] = {}
        for game in self._extract_games(scoreboard):
            state = str(game.get("state", "")).lower()
            round_name = game.get("round")
            for side in ("home_name", "away_name"):
                name = game.get(side)
                if not name:
                    continue
                norm = self.mapper.resolve_external_name(name) or self.mapper.normalize(name)
                in_live = state in {"live", "in_progress"}
                upcoming = state in {"pre", "scheduled", "preview"}
                finalish = state in {"final", "complete"}
                out[norm] = TeamTournamentState(
                    team_name=name,
                    normalized_team_name=norm,
                    alive=not finalish,
                    in_live_game=in_live,
                    has_upcoming_game=upcoming,
                    current_round=round_name,
                    game_id=game.get("game_id"),
                    next_game_start_ts=_parse_start_ts(game.get("start_time")),
                    eliminated_round=round_name if finalish else None,
                    fixed_settlement=None,
                    ncaa_status_mode=("live" if in_live else "upcoming" if upcoming else "final_pending_bracket" if finalish else "alive_idle"),
                    last_status_ts=now,
                )
        return out

    def refresh_bracket_truth(self, bracket_payload: dict[str, Any], team_states: dict[str, TeamTournamentState]) -> dict[str, TeamTournamentState]:
        resolved = {k: v for k, v in team_states.items()}
        for team_name, info in self.infer_team_round_status(bracket_payload).items():
            norm = self.mapper.resolve_external_name(team_name) or self.mapper.normalize(team_name)
            current = resolved.get(norm)
            eliminated_round = info.get("eliminated_round")
            is_alive = not bool(eliminated_round)
            fixed = SETTLEMENT_BY_LOSS_ROUND.get(eliminated_round) if eliminated_round else None
            mode = "alive_idle" if is_alive else "eliminated_fixed"
            resolved[norm] = TeamTournamentState(
                team_name=current.team_name if current else team_name,
                normalized_team_name=norm,
                alive=is_alive,
                in_live_game=current.in_live_game if current else False,
                has_upcoming_game=current.has_upcoming_game if current else False,
                current_round=info.get("current_round") or (current.current_round if current else None),
                game_id=current.game_id if current else None,
                next_game_start_ts=current.next_game_start_ts if current else None,
                eliminated_round=eliminated_round,
                fixed_settlement=fixed,
                ncaa_status_mode=mode,
                last_status_ts=time.time(),
            )
        return resolved

    def infer_team_round_status(self, bracket_payload: dict[str, Any]) -> dict[str, dict[str, str | None]]:
        # permissive parser: supports varying bracket JSON shapes.
        out: dict[str, dict[str, str | None]] = {}
        games = bracket_payload.get("games") if isinstance(bracket_payload, dict) else None
        if isinstance(games, list):
            for g in games:
                round_name = g.get("round") or g.get("bracketRound")
                winner = g.get("winner") or {}
                loser = g.get("loser") or {}
                winner_name = winner.get("name") or winner.get("shortName")
                loser_name = loser.get("name") or loser.get("shortName")
                if winner_name:
                    out[winner_name] = {"current_round": round_name, "eliminated_round": None}
                if loser_name:
                    out[loser_name] = {"current_round": round_name, "eliminated_round": round_name}
        return out

    @staticmethod
    def _extract_games(scoreboard_json: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in scoreboard_json:
            game_id = str(row.get("gameID") or row.get("id") or "")
            home = row.get("home") or row.get("homeTeam") or {}
            away = row.get("away") or row.get("awayTeam") or {}
            home_name = home.get("names", {}).get("short") or home.get("shortName") or home.get("name")
            away_name = away.get("names", {}).get("short") or away.get("shortName") or away.get("name")
            if not (game_id and home_name and away_name):
                continue
            out.append(
                {
                    "game_id": game_id,
                    "home_name": home_name,
                    "away_name": away_name,
                    "state": str(row.get("gameState") or row.get("status") or "").lower(),
                    "round": row.get("bracketRound"),
                    "start_time": row.get("startTime") or row.get("startDate"),
                }
            )
        return out


def _parse_start_ts(value: Any) -> float | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return dt.datetime.fromisoformat(text).timestamp()
        except Exception:
            return None
    return None
