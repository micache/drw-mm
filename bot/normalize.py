from __future__ import annotations

import re

_ALIAS_MAP = {
    "uconn": "connecticut",
    "unc": "north carolina",
    "ole miss": "mississippi",
    "byu": "brigham young",
    "lsu": "louisiana state",
}


def normalize_team_name(name: str) -> str:
    value = name.lower().strip()
    value = re.sub(r"[^a-z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value)
    return _ALIAS_MAP.get(value, value)
