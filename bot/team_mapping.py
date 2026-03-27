from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MappingError:
    symbol: str
    reason: str
    detail: str


def normalize_team_name(name: str) -> str:
    s = (name or "").lower().strip()
    s = s.replace("st.", "st")
    s = s.replace("saint", "st")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(university|college)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass
class TeamMapper:
    symbol_to_normalized: dict[str, str] = field(default_factory=dict)
    normalized_to_symbol: dict[str, str] = field(default_factory=dict)
    unresolved_symbols: set[str] = field(default_factory=set)
    aliases: dict[str, str] = field(
        default_factory=lambda: {
            "uconn": "connecticut",
            "unc": "north carolina",
            "n carolina": "north carolina",
            "ole miss": "mississippi",
            "miami": "miami",
            "miami fl": "miami",
            "miami oh": "miami oh",
            "st johns": "st johns",
            "st john s": "st johns",
            "saint johns": "st johns",
            "st marys": "st marys",
            "st mary s": "st marys",
            "saint marys": "st marys",
            "michigan st": "michigan st",
            "iowa st": "iowa st",
            "ohio st": "ohio st",
            "utah st": "utah st",
            "wright st": "wright st",
            "tennessee st": "tennessee st",
            "north dakota st": "north dakota st",
            "nc state": "nc state",
        }
    )

    def normalize(self, name: str) -> str:
        base = normalize_team_name(name)
        return self.aliases.get(base, base)

    def register_symbol(self, symbol: str, team_name: str) -> None:
        norm = self.normalize(team_name)
        self.symbol_to_normalized[symbol] = norm
        self.normalized_to_symbol.setdefault(norm, symbol)

    def symbol_to_norm(self, symbol: str) -> str | None:
        if symbol in self.unresolved_symbols:
            return None
        return self.symbol_to_normalized.get(symbol)

    def norm_to_symbol(self, normalized_name: str) -> str | None:
        return self.normalized_to_symbol.get(normalized_name)

    def resolve_external_name(self, name: str) -> str | None:
        norm = self.normalize(name)
        if norm in self.normalized_to_symbol:
            return norm
        compact = norm.replace(" ", "")
        for key in self.normalized_to_symbol:
            if key.replace(" ", "") == compact:
                return key
        for candidate in _candidate_team_names(norm):
            if candidate in self.normalized_to_symbol:
                return candidate
            compact_candidate = candidate.replace(" ", "")
            for key in self.normalized_to_symbol:
                if key.replace(" ", "") == compact_candidate:
                    return key
        return None


_COMMON_MASCOT_TOKENS = {
    "eagles",
    "hawks",
    "wildcats",
    "bulldogs",
    "bearcats",
    "bears",
    "tigers",
    "lions",
    "wolves",
    "wolfpack",
    "knights",
    "huskies",
    "bruins",
    "spartans",
    "mustangs",
    "cougars",
    "rams",
    "devils",
    "blue",
    "bluejays",
    "jays",
    "hawks",
    "pirates",
    "raiders",
    "cavaliers",
    "volunteers",
    "longhorns",
    "illini",
    "jayhawks",
    "aggies",
    "terrapins",
    "cyclones",
    "wolverines",
    "cardinals",
    "panthers",
    "trojans",
    "horned",
    "frogs",
    "redhawks",
    "buckeyes",
    "boilermakers",
    "gaels",
    "demon",
    "deacons",
    "storm",
    "johnnies",
    "orange",
    "hoosiers",
    "badgers",
    "tar",
    "heels",
}


def _candidate_team_names(norm: str) -> list[str]:
    tokens = [t for t in norm.split(" ") if t]
    if not tokens:
        return []

    # Generate progressively shorter candidates by stripping likely mascot
    # suffix words from external feeds (e.g. "byu cougars" -> "byu").
    out: list[str] = []
    working = list(tokens)
    while len(working) > 1 and working[-1] in _COMMON_MASCOT_TOKENS:
        working = working[:-1]
        candidate = " ".join(working)
        if candidate and candidate not in out:
            out.append(candidate)

    # Also try dropping only the final token once for generic suffixes not in
    # the allowlist above.
    if len(tokens) > 1:
        one_drop = " ".join(tokens[:-1])
        if one_drop and one_drop not in out:
            out.append(one_drop)
    return out


def validate_symbol_mapping(
    contracts: dict[str, object],
    playoffstatus_rows: dict[str, object],
    ncaa_teams: set[str],
    odds_teams: set[str],
) -> list[MappingError]:
    errors: list[MappingError] = []
    for symbol, contract in contracts.items():
        norm = getattr(contract, "normalized_team_name", None)
        if not norm:
            errors.append(MappingError(symbol, "missing_normalized_name", "no canonical name"))
            continue
        matches = 1 if norm in playoffstatus_rows else 0
        if matches != 1:
            errors.append(MappingError(symbol, "missing_playoffstatus_row", f"{norm} not found"))
        if norm not in ncaa_teams:
            errors.append(MappingError(symbol, "missing_ncaa_mapping", f"{norm} not in ncaa feed"))
        if norm not in odds_teams:
            errors.append(MappingError(symbol, "missing_odds_mapping", f"{norm} not in odds feed"))
    return errors
