from __future__ import annotations

import logging
import statistics
import time
from typing import Any

import aiohttp

from bot.models import LiveGameProb
from bot.team_mapping import TeamMapper

logger = logging.getLogger(__name__)


class LiveOddsSource:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str, sport_key: str, mapper: TeamMapper) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.sport_key = sport_key
        self.mapper = mapper
        self._last_home_prob: dict[str, float] = {}
        self._warned_missing_api_key = False

    async def fetch_games_odds(self) -> list[dict[str, Any]]:
        if not self.api_key:
            if not self._warned_missing_api_key:
                logger.warning("ODDS_API_KEY is empty; live odds source disabled")
                self._warned_missing_api_key = True
            return []
        url = f"{self.base_url}/sports/{self.sport_key}/odds"
        params = {"apiKey": self.api_key, "regions": "us", "markets": "h2h", "oddsFormat": "decimal"}
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.warning("odds request failed status=%s body=%s", resp.status, body[:300])
                    return []
                data = await resp.json()
                return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("odds request exception: %s", exc)
            return []

    def extract_moneyline_probs(self, raw_game: dict[str, Any]) -> LiveGameProb | None:
        home = raw_game.get("home_team")
        away = raw_game.get("away_team")
        if not home or not away:
            return None
        game_id = str(raw_game.get("id") or f"{home}-{away}")
        home_norm = self.mapper.resolve_external_name(home) or self.mapper.normalize(home)
        away_norm = self.mapper.resolve_external_name(away) or self.mapper.normalize(away)

        home_probs: list[float] = []
        away_probs: list[float] = []
        staleness: list[float] = []
        now = time.time()
        for bookmaker in raw_game.get("bookmakers", []):
            updated = bookmaker.get("last_update")
            if updated:
                try:
                    staleness.append(max(0.0, now - _to_ts(updated)))
                except Exception:
                    pass
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcome = {x.get("name"): x for x in market.get("outcomes", [])}
                if home not in outcome or away not in outcome:
                    continue
                p_home = self._implied_prob(outcome[home].get("price"), outcome[home].get("american"))
                p_away = self._implied_prob(outcome[away].get("price"), outcome[away].get("american"))
                if p_home <= 0 or p_away <= 0:
                    continue
                denom = p_home + p_away
                home_probs.append(p_home / denom)
                away_probs.append(p_away / denom)

        if not home_probs:
            return None

        home_med = statistics.median(home_probs)
        away_med = statistics.median(away_probs)
        total = home_med + away_med
        if total <= 0:
            return None
        home_win = home_med / total
        away_win = away_med / total
        prev = self._last_home_prob.get(game_id, home_win)
        delta = home_win - prev
        self._last_home_prob[game_id] = home_win

        bookmakers = len(home_probs)
        median_staleness = statistics.median(staleness) if staleness else None
        score = min(1.0, bookmakers / 8.0)
        if median_staleness is not None:
            score *= 1.0 if median_staleness <= 30 else 0.6

        return LiveGameProb(
            game_id=game_id,
            home_team_normalized=home_norm,
            away_team_normalized=away_norm,
            home_win_prob=home_win,
            away_win_prob=away_win,
            bookmakers_used=bookmakers,
            source_timestamp=now,
            is_fresh=(median_staleness is None or median_staleness <= 120),
            is_live=bool(raw_game.get("commence_time") is None),
            odds_quality_score=score,
            median_staleness_seconds=median_staleness,
            delta_home_win_prob=delta,
        )

    @staticmethod
    def _implied_prob(decimal_price: float | None, american_price: float | None) -> float:
        if decimal_price and decimal_price > 1:
            return 1.0 / float(decimal_price)
        if american_price:
            odds = float(american_price)
            if odds > 0:
                return 100.0 / (odds + 100.0)
            return (-odds) / ((-odds) + 100.0)
        return 0.0


def _to_ts(value: str) -> float:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    from datetime import datetime

    return datetime.fromisoformat(value).timestamp()
