from __future__ import annotations

import csv
import io
import re
import time

import aiohttp

from bot.models import TeamProbabilities
from bot.team_mapping import TeamMapper


class PlayoffStatusSource:
    def __init__(self, session: aiohttp.ClientSession, url: str, mapper: TeamMapper) -> None:
        self.session = session
        self.url = url
        self.mapper = mapper
        self._last_good: dict[str, TeamProbabilities] = {}

    async def refresh(self) -> dict[str, TeamProbabilities]:
        async with self.session.get(self.url) as resp:
            if resp.status >= 400:
                return self._last_good
            html = await resp.text()

        table_csv = self._html_table_to_csv(html)
        if not table_csv:
            return self._last_good

        parsed: dict[str, TeamProbabilities] = {}
        now = time.time()
        for row in csv.DictReader(io.StringIO(table_csv)):
            team = row.get("Team") or row.get("team")
            if not team:
                continue
            norm = self.mapper.normalize(team)
            p_r32 = self._pct(row, ["R32", "Round 32", "R2"])
            p_s16 = self._pct(row, ["Sweet 16", "S16"])
            p_e8 = self._pct(row, ["Elite 8", "E8"])
            p_f4 = self._pct(row, ["Final 4", "F4"])
            p_final = self._pct(row, ["Final", "Title"])
            p_champ = self._pct(row, ["Champion", "Champ"])
            p_r32, p_s16, p_e8, p_f4, p_final, p_champ = self._monotonic(p_r32, p_s16, p_e8, p_f4, p_final, p_champ)
            baseline = self.compute_baseline_fv(p_r32, p_s16, p_e8, p_f4, p_final, p_champ)
            parsed[norm] = TeamProbabilities(
                team_name=team,
                normalized_team_name=norm,
                p_r32=p_r32,
                p_s16=p_s16,
                p_e8=p_e8,
                p_f4=p_f4,
                p_final=p_final,
                p_champion=p_champ,
                baseline_fv=baseline,
                source_timestamp=now,
            )
        if parsed:
            self._last_good = parsed
        return self._last_good

    @staticmethod
    def compute_baseline_fv(p_r32: float, p_s16: float, p_e8: float, p_f4: float, p_final: float, p_champion: float) -> float:
        return (
            64 * p_champion
            + 32 * (p_final - p_champion)
            + 16 * (p_f4 - p_final)
            + 8 * (p_e8 - p_f4)
            + 4 * (p_s16 - p_e8)
            + 2 * (p_r32 - p_s16)
        )

    @staticmethod
    def _pct(row: dict[str, str], keys: list[str]) -> float:
        for key in keys:
            if key in row and row[key]:
                try:
                    return float(row[key].replace("%", "").strip()) / 100.0
                except ValueError:
                    pass
        return 0.0

    @staticmethod
    def _monotonic(*vals: float) -> tuple[float, ...]:
        out = list(vals)
        for i in range(1, len(out)):
            out[i] = min(out[i - 1], max(0.0, min(1.0, out[i])))
        out[0] = max(0.0, min(1.0, out[0]))
        return tuple(out)

    @staticmethod
    def _html_table_to_csv(html: str) -> str:
        match = re.search(r"<table[^>]*>(.*?)</table>", html, flags=re.I | re.S)
        if not match:
            return ""
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", match.group(1), flags=re.I | re.S)
        lines: list[str] = []
        for row in rows:
            cols = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.I | re.S)
            if not cols:
                continue
            vals = [re.sub(r"<[^>]+>", "", c).strip().replace(",", "") for c in cols]
            lines.append(",".join(vals))
        return "\n".join(lines)
