from __future__ import annotations

import asyncio
import csv
import io
import logging
import re

import aiohttp

from bot.normalize import normalize_team_name

logger = logging.getLogger(__name__)


class ProbabilitySource:
    def __init__(self, session: aiohttp.ClientSession, url: str) -> None:
        self._session = session
        self._url = url
        self._last_good: dict[str, dict[str, float]] = {}

    async def fetch_probabilities(self) -> dict[str, dict[str, float]]:
        html = await self._fetch_html()
        if not html:
            return self._last_good

        table = self._extract_first_csv_like_table(html)
        if not table:
            return self._last_good

        parsed = self._parse_table(table)
        if parsed:
            self._last_good = parsed
        return self._last_good

    async def _fetch_html(self) -> str:
        try:
            async with self._session.get(self._url) as resp:
                resp.raise_for_status()
                return await resp.text()
        except Exception as exc:
            logger.warning("Failed to fetch playoff probabilities: %s", exc)
            await asyncio.sleep(0)
            return ""

    @staticmethod
    def _extract_first_csv_like_table(html: str) -> str:
        match = re.search(r"<table[^>]*>(.*?)</table>", html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        table_html = match.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL)
        table_lines: list[str] = []
        for row in rows:
            cols = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.IGNORECASE | re.DOTALL)
            values = [re.sub(r"<[^>]+>", "", c).strip() for c in cols]
            if values:
                table_lines.append(",".join(v.replace(",", "") for v in values))
        return "\n".join(table_lines)

    @staticmethod
    def _parse_table(text: str) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            team = row.get("Team") or row.get("team") or row.get("School")
            if not team:
                continue
            normalized = normalize_team_name(team)
            values: dict[str, float] = {}
            for key, value in row.items():
                if key is None or value is None:
                    continue
                stripped = value.strip().replace("%", "")
                if not stripped:
                    continue
                try:
                    values[key.strip()] = float(stripped) / 100.0
                except ValueError:
                    continue
            if values:
                result[normalized] = values
        return result


def baseline_ev_from_probs(prob_row: dict[str, float]) -> float:
    payout_map = {
        "R64": 0,
        "R32": 0,
        "Sweet 16": 2,
        "Elite 8": 4,
        "Final 4": 8,
        "Final": 16,
        "Champion": 64,
    }
    ev = 0.0
    for key, payout in payout_map.items():
        prob = prob_row.get(key)
        if prob is not None:
            ev += prob * payout
    if ev <= 0:
        # fallback if column names differ
        values = list(prob_row.values())
        if values:
            ev = 64.0 * max(values)
    return max(0.0, min(64.0, ev))
