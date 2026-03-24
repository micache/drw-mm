from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from bot.models import TeamTournamentState
from bot.team_mapping import TeamMapper


ROUND_BY_DATE_2026 = [
    (dt.date(2026, 3, 17), dt.date(2026, 3, 18), "FIRST_FOUR"),
    (dt.date(2026, 3, 19), dt.date(2026, 3, 22), "ROUND_64"),
    (dt.date(2026, 3, 26), dt.date(2026, 3, 27), "SWEET_16"),
    (dt.date(2026, 3, 28), dt.date(2026, 3, 29), "ELITE_8"),
    (dt.date(2026, 4, 4), dt.date(2026, 4, 4), "FINAL_FOUR"),
    (dt.date(2026, 4, 6), dt.date(2026, 4, 6), "FINAL"),
]
SETTLEMENT_BY_LOSS_ROUND = {
    "FIRST_FOUR": 0.0,
    "ROUND_64": 0.0,
    "ROUND_32": 2.0,
    "SWEET_16": 4.0,
    "ELITE_8": 8.0,
    "FINAL_FOUR": 16.0,
    "FINAL": 32.0,
}


@dataclass(frozen=True)
class NcaaGame:
    game_id: str
    home_team: str
    away_team: str
    game_state: str
    bracket_round: str | None


class NcaaSource:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, mapper: TeamMapper) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.mapper = mapper

    async def fetch_scoreboard(self, date_or_path: str | None = None) -> list[dict[str, Any]]:
        date_or_path = date_or_path or dt.date.today().isoformat()
        url = f"{self.base_url}/scoreboard/basketball-men/d1/{date_or_path}"
        async with self.session.get(url) as resp:
            if resp.status >= 400:
                return []
            payload = await resp.json()
        return payload if isinstance(payload, list) else payload.get("games", [])

    def extract_live_games(self, scoreboard_json: list[dict[str, Any]]) -> list[NcaaGame]:
        return [g for g in self._extract_games(scoreboard_json) if g.game_state.lower() in {"live", "in_progress"}]

    def extract_finished_games(self, scoreboard_json: list[dict[str, Any]]) -> list[NcaaGame]:
        return [g for g in self._extract_games(scoreboard_json) if g.game_state.lower() in {"final", "complete"}]

    async def fetch_game(self, game_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/game/{game_id}"
        async with self.session.get(url) as resp:
            if resp.status >= 400:
                return {}
            return await resp.json()

    def refresh_team_live_status(self, scoreboard: list[dict[str, Any]]) -> dict[str, TeamTournamentState]:
        now = time.time()
        games = self._extract_games(scoreboard)
        live_ids = {g.game_id for g in self.extract_live_games(scoreboard)}
        team_states: dict[str, TeamTournamentState] = {}
        for game in games:
            game_round = game.bracket_round or self._round_from_date(dt.date.today())
            for name in (game.home_team, game.away_team):
                norm = self.mapper.resolve_external_name(name) or self.mapper.normalize(name)
                is_live = game.game_id in live_ids
                game_done = game.game_state.lower() in {"final", "complete"}
                team_states[norm] = TeamTournamentState(
                    team_name=name,
                    normalized_team_name=norm,
                    alive=not game_done,
                    in_live_game=is_live,
                    current_round=game_round,
                    game_id=game.game_id,
                    eliminated_round=game_round if game_done else None,
                    fixed_settlement=SETTLEMENT_BY_LOSS_ROUND.get(game_round) if game_done else None,
                    last_status_ts=now,
                )
        return team_states

    def _extract_games(self, scoreboard_json: list[dict[str, Any]]) -> list[NcaaGame]:
        out: list[NcaaGame] = []
        for row in scoreboard_json:
            game_id = str(row.get("gameID") or row.get("id") or "")
            home = row.get("home") or row.get("homeTeam") or {}
            away = row.get("away") or row.get("awayTeam") or {}
            home_name = home.get("names", {}).get("short") or home.get("shortName") or home.get("name")
            away_name = away.get("names", {}).get("short") or away.get("shortName") or away.get("name")
            if not (game_id and home_name and away_name):
                continue
            out.append(
                NcaaGame(
                    game_id=game_id,
                    home_team=home_name,
                    away_team=away_name,
                    game_state=str(row.get("gameState") or row.get("status") or ""),
                    bracket_round=row.get("bracketRound"),
                )
            )
        return out

    @staticmethod
    def _round_from_date(current: dt.date) -> str:
        for start, end, round_name in ROUND_BY_DATE_2026:
            if start <= current <= end:
                return round_name
        return "ROUND_32"
