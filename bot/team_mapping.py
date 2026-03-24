from __future__ import annotations

import re
from dataclasses import dataclass, field


def _clean(value: str) -> str:
    s = value.lower().strip()
    s = s.replace("st.", "state").replace(" st ", " state ")
    s = s.replace("saint", "st")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(university|college)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass
class TeamMapper:
    symbol_to_normalized: dict[str, str] = field(default_factory=dict)
    normalized_to_symbol: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=lambda: {
        "uconn": "connecticut",
        "unc": "north carolina",
        "ole miss": "mississippi",
        "usc": "southern california",
        "st johns": "st john s",
    })

    def normalize(self, name: str) -> str:
        base = _clean(name)
        return self.aliases.get(base, base)

    def register_symbol(self, symbol: str, team_name: str) -> None:
        norm = self.normalize(team_name)
        self.symbol_to_normalized[symbol] = norm
        self.normalized_to_symbol.setdefault(norm, symbol)

    def symbol_to_norm(self, symbol: str) -> str | None:
        return self.symbol_to_normalized.get(symbol)

    def norm_to_symbol(self, normalized_name: str) -> str | None:
        return self.normalized_to_symbol.get(normalized_name)

    def resolve_external_name(self, name: str) -> str | None:
        norm = self.normalize(name)
        if norm in self.normalized_to_symbol:
            return norm
        # strict fallback on compact keys
        compact = norm.replace(" ", "")
        for key in self.normalized_to_symbol:
            if key.replace(" ", "") == compact:
                return key
        return None
