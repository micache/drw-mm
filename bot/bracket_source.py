from __future__ import annotations

import asyncio
import logging
import re
from typing import Iterable

import aiohttp

from bot.models import BracketState
from bot.normalize import normalize_team_name

logger = logging.getLogger(__name__)


class BracketSource:
    def __init__(self, session: aiohttp.ClientSession, url: str = "https://www.ncaa.com/brackets/basketball-men/d1") -> None:
        self._session = session
        self._url = url

    async def fetch_states(self) -> dict[str, BracketState]:
        html = await self._fetch_html()
        if not html:
            return {}

        states: dict[str, BracketState] = {}
        eliminated_matches = re.findall(r"([A-Za-z .'-]+)\s+eliminated", html, flags=re.IGNORECASE)
        alive_matches = re.findall(r"team-name\">([A-Za-z .'-]+)<", html, flags=re.IGNORECASE)

        for name in set(self._clean(eliminated_matches)):
            norm = normalize_team_name(name)
            states[norm] = BracketState(
                team_name=name,
                normalized_team_name=norm,
                status="eliminated",
                current_round=None,
                eliminated_round=None,
                settlement_if_known=0.0,
            )

        for name in set(self._clean(alive_matches)):
            norm = normalize_team_name(name)
            states.setdefault(
                norm,
                BracketState(
                    team_name=name,
                    normalized_team_name=norm,
                    status="alive",
                    current_round=None,
                    eliminated_round=None,
                    settlement_if_known=None,
                ),
            )
        return states

    async def _fetch_html(self) -> str:
        try:
            async with self._session.get(self._url) as resp:
                resp.raise_for_status()
                return await resp.text()
        except Exception as exc:
            logger.warning("Failed to fetch official bracket state: %s", exc)
            await asyncio.sleep(0)
            return ""

    @staticmethod
    def _clean(names: Iterable[str]) -> list[str]:
        out: list[str] = []
        for name in names:
            clean = re.sub(r"\s+", " ", name).strip()
            if clean:
                out.append(clean)
        return out
