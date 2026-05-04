from __future__ import annotations

from datetime import datetime, timedelta, timezone

import yfinance as yf
from dateutil import parser as dateparser

from config import DEFAULT_TICKERS

# yfinance scrapes Yahoo and may break if Yahoo changes pages; swap to a
# paid/official market data provider if reliability becomes important.

MATERIAL_KEYWORDS = [
    "earnings",
    "revenue",
    "guidance",
    "forecast",
    "outlook",
    "acquisition",
    "merger",
    "m&a",
    "partnership",
    "analyst",
    "upgrade",
    "downgrade",
    "rating",
    "price target",
    "regulation",
    "regulatory",
    "lawsuit",
    "settlement",
    "sec",
    "ftc",
]

ALIASES = {
    "META": ["meta", "facebook", "instagram", "whatsapp"],
    "RBLX": ["roblox", "rblx"],
}


def _published_at(item: dict) -> datetime | None:
    content = item.get("content", item)
    value = content.get("pubDate") or content.get("providerPublishTime")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = dateparser.parse(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _material_headline(ticker: str, pct_change: float, news: list[dict]) -> str | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    aliases = ALIASES.get(ticker, [ticker.lower()])
    for item in news:
        content = item.get("content", item)
        title = content.get("title", "")
        if not title:
            continue
        published = _published_at(item)
        if published and published < cutoff:
            continue
        lower = title.lower()
        about_ticker = ticker.lower() in lower or any(alias in lower for alias in aliases)
        material = any(keyword in lower for keyword in MATERIAL_KEYWORDS) or abs(pct_change) > 3
        if about_ticker and material:
            return title
    return None


def get_stock(ticker: str) -> dict | None:
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        price = float(info.last_price)
        previous_close = float(info.previous_close)
        pct_change = ((price - previous_close) / previous_close) * 100
        news = []
        try:
            news = stock.news or []
        except Exception:
            pass
        return {
            "ticker": ticker,
            "price": round(price, 2),
            "pct_change": round(pct_change, 2),
            "material_news": _material_headline(ticker, pct_change, news),
        }
    except Exception:
        return None


def get_stocks(tickers: list[str] | None = None) -> list[dict]:
    results = []
    for ticker in tickers or DEFAULT_TICKERS:
        result = get_stock(ticker)
        if result:
            results.append(result)
    return results
