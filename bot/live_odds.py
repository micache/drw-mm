from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

from bot.models import GameState
from bot.normalize import normalize_team_name

logger = logging.getLogger(__name__)


class LiveOddsSource:
    def __init__(self, session: aiohttp.ClientSession, api_base: str, api_key: str | None) -> None:
        self._session = session
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key

    async def fetch_live_probs(self) -> dict[str, GameState]:
        if not self._api_key:
            return {}
        url = f"{self._api_base}/sports/basketball_ncaab/odds"
        params = {
            "apiKey": self._api_key,
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "eventIds": "",
        }
        try:
            async with self._session.get(url, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch live odds: %s", exc)
            await asyncio.sleep(0)
            return {}

        games: dict[str, GameState] = {}
        now = time.time()
        for game in data if isinstance(data, list) else []:
            home = game.get("home_team")
            away = game.get("away_team")
            if not home or not away:
                continue
            probs_home: list[float] = []
            probs_away: list[float] = []
            for book in game.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    price_by_team = {o.get("name"): float(o.get("price", 0.0)) for o in market.get("outcomes", [])}
                    if home not in price_by_team or away not in price_by_team:
                        continue
                    p_home = 1.0 / max(price_by_team[home], 1e-6)
                    p_away = 1.0 / max(price_by_team[away], 1e-6)
                    denom = p_home + p_away
                    if denom <= 0:
                        continue
                    probs_home.append(p_home / denom)
                    probs_away.append(p_away / denom)

            if not probs_home or not probs_away:
                continue
            p_home = sum(probs_home) / len(probs_home)
            p_away = sum(probs_away) / len(probs_away)
            game_state = GameState(
                team_a=home,
                team_b=away,
                p_team_a=p_home,
                p_team_b=p_away,
                timestamp=now,
                bookmaker_count=len(probs_home),
                confidence="high" if len(probs_home) >= 3 else "medium",
            )
            games[normalize_team_name(home)] = game_state
            games[normalize_team_name(away)] = game_state
        return games
