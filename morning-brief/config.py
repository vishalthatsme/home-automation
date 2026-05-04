from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")

NOTE_TITLE = "Family Morning Briefing"
TIMEZONE = "America/Los_Angeles"
LOCAL_TZ = ZoneInfo(TIMEZONE)

WEATHER_LAT = 37.5485
WEATHER_LON = -121.9886
DEFAULT_TICKERS = ["META", "RBLX"]
DEFAULT_RETENTION_DAYS = 30
CALENDAR_SOURCE = os.getenv("CALENDAR_SOURCE", "auto").strip().lower() or "auto"
GMAIL_SOURCE = os.getenv("GMAIL_SOURCE", "auto").strip().lower() or "auto"
GOOGLE_CALENDAR_URL = os.getenv(
    "GOOGLE_CALENDAR_URL", "https://calendar.google.com/calendar/u/0/r/day"
)
GMAIL_URL = os.getenv("GMAIL_URL", "https://mail.google.com/mail/u/0")
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}

LOG_DIR = APP_DIR / "log"
OUT_DIR = APP_DIR / "out"
for directory in (LOG_DIR, OUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def preference_text() -> str:
    path = APP_DIR / "preferences.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""
