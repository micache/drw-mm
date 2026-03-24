from __future__ import annotations

import os
from pathlib import Path

GAME_ID = int(os.getenv("DRW_GAME_ID", "0"))
TOKEN = os.getenv("DRW_TOKEN", "")
BASE_URL = os.getenv("DRW_BASE_URL", "https://games.drw")

PLAYOFFSTATUS_URL = os.getenv(
    "PLAYOFFSTATUS_URL",
    "https://www.playoffstatus.com/ncaabasketball/ncaabasketballtournperformprob.html",
)
NCAA_API_BASE = os.getenv("NCAA_API_BASE", "https://ncaa-api.henrygd.me")
ODDS_API_BASE = os.getenv("ODDS_API_BASE", "https://api.the-odds-api.com/v4")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_SPORT_KEY = "basketball_ncaab"

ORDER_TYPE = os.getenv("SIM_ORDER_TYPE", "LIMIT")
DRY_RUN = os.getenv("BOT_DRY_RUN", "true").lower() == "true"

ACCOUNT_RESYNC_SECONDS = float(os.getenv("ACCOUNT_RESYNC_SECONDS", "1"))
NOTIFICATION_RESYNC_SECONDS = float(os.getenv("NOTIFICATION_RESYNC_SECONDS", "30"))
PLAYOFFSTATUS_REFRESH_SECONDS = float(os.getenv("PLAYOFFSTATUS_REFRESH_SECONDS", "3600"))
NCAA_REFRESH_LIVE_SECONDS = float(os.getenv("NCAA_REFRESH_LIVE_SECONDS", "20"))
NCAA_REFRESH_IDLE_SECONDS = float(os.getenv("NCAA_REFRESH_IDLE_SECONDS", "120"))
LIVE_ODDS_REFRESH_SECONDS = float(os.getenv("LIVE_ODDS_REFRESH_SECONDS", "10"))
CSV_DEBOUNCE_SECONDS = float(os.getenv("CSV_DEBOUNCE_SECONDS", "1"))

MAX_ABS_POSITION = int(os.getenv("MAX_ABS_POSITION", "100"))
LIVE_MAX_POSITION = int(os.getenv("LIVE_MAX_POSITION", "10"))
ELIMINATED_MIN_EDGE = float(os.getenv("ELIMINATED_MIN_EDGE", "0.25"))
BASKET_MIN_EDGE = float(os.getenv("BASKET_MIN_EDGE", "1.0"))
LIVE_ENTRY_BUFFER = float(os.getenv("LIVE_ENTRY_BUFFER", "1.0"))
ODDS_FRESHNESS_SECONDS = float(os.getenv("ODDS_FRESHNESS_SECONDS", "20"))
ODDS_JUMP_CIRCUIT_BREAKER = float(os.getenv("ODDS_JUMP_CIRCUIT_BREAKER", "0.04"))
WORST_CASE_BUFFER = float(os.getenv("WORST_CASE_BUFFER", "25000"))

OUT_DIR = Path(os.getenv("OUT_DIR", "./out"))
POSITIONS_CSV = OUT_DIR / "positions.csv"
ORDERS_CSV = OUT_DIR / "open_orders.csv"
FILLS_CSV = OUT_DIR / "fills.csv"
FAIR_VALUES_CSV = OUT_DIR / "fair_values.csv"
