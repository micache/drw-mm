from __future__ import annotations

import time
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from bot.models import TeamProbabilities
from bot.team_mapping import TeamMapper


class PlayoffStatusSource:
    def __init__(self, session: aiohttp.ClientSession, url: str, mapper: TeamMapper) -> None:
        self.session = session
        self.url = url
        self.mapper = mapper
        self._last_good: dict[str, TeamProbabilities] = {}

    async def refresh(self) -> dict[str, TeamProbabilities]:
        try:
            async with self.session.get(self.url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status >= 400:
                    return self._last_good
                html = await resp.text()
        except Exception:
            return self._last_good

        rows = self._parse_rows(html)
        if not rows:
            return self._last_good

        parsed: dict[str, TeamProbabilities] = {}
        now = time.time()
        for row in rows:
            team = row["team"]
            norm = self.mapper.normalize(team)
            p_vals = [
                self._parse_pct(row["prob_round_2"]),
                self._parse_pct(row["prob_sweet_sixteen"]),
                self._parse_pct(row["prob_elite_eight"]),
                self._parse_pct(row["prob_final_four"]),
                self._parse_pct(row["prob_championship_game"]),
                self._parse_pct(row["prob_national_champion"]),
            ]
            p_r32, p_s16, p_e8, p_f4, p_final, p_champ = self._monotonic(*p_vals)
            if p_r32 <= 0 and p_s16 <= 0 and p_e8 <= 0 and p_f4 <= 0 and p_final <= 0 and p_champ <= 0:
                continue

            parsed[norm] = TeamProbabilities(
                team_name=team,
                normalized_team_name=norm,
                p_r32=p_r32,
                p_s16=p_s16,
                p_e8=p_e8,
                p_f4=p_f4,
                p_final=p_final,
                p_champion=p_champ,
                baseline_fv=self.compute_baseline_fv(p_r32, p_s16, p_e8, p_f4, p_final, p_champ),
                source_timestamp=now,
                parsed_ok=True,
                raw_team_name=team,
                canonical_team_name=norm,
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

    def _parse_rows(self, html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("div.mncntnt table")
        if table is None:
            return []
        tr_list = table.find_all("tr")
        out: list[dict[str, str]] = []
        for tr in tr_list[2:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 13:
                continue
            team_link = cells[0].find("a")
            if team_link is None:
                continue

            def clean(v: str) -> str:
                return " ".join(v.replace("\xa0", " ").split())

            out.append(
                {
                    "team": clean(team_link.get_text(" ", strip=True)),
                    "prob_national_champion": clean(cells[6].get_text(" ", strip=True)),
                    "prob_championship_game": clean(cells[7].get_text(" ", strip=True)),
                    "prob_final_four": clean(cells[8].get_text(" ", strip=True)),
                    "prob_elite_eight": clean(cells[9].get_text(" ", strip=True)),
                    "prob_sweet_sixteen": clean(cells[10].get_text(" ", strip=True)),
                    "prob_round_2": clean(cells[11].get_text(" ", strip=True)),
                }
            )
        return out

    @staticmethod
    def _parse_pct(raw: str) -> float:
        cell = raw.strip().replace("%", "")
        if not cell:
            return 0.0
        if cell == "^":
            return 1.0
        if cell in {"X", "x"}:
            return 0.0
        if cell.startswith("<"):
            return 0.005
        try:
            return float(cell) / 100.0
        except ValueError:
            return 0.0

    @staticmethod
    def _monotonic(*vals: float) -> tuple[float, ...]:
        out = [max(0.0, min(1.0, x)) for x in vals]
        for i in range(1, len(out)):
            out[i] = min(out[i - 1], out[i])
        return tuple(out)
