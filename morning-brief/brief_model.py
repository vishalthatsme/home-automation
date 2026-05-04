from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from calendar_reader import detect_calendar_headsups, format_event_time

SEPARATOR = "————————————————————————"


def _format_event(event: dict[str, Any]) -> str:
    title = event.get("title") or "(untitled)"
    when = format_event_time(event)
    location = event.get("location")
    if location and any(term in f"{title} {location}".lower() for term in ["doctor", "dentist", "school", "soccer", "point", "park"]):
        return f"- {when}: {title} ({location})"
    return f"- {when}: {title}"


def _format_email(email: dict[str, Any]) -> str:
    return f"- {email.get('sender', 'Unknown sender')}: {email.get('subject', '(no subject)')}"


def _format_stock(stock: dict[str, Any]) -> str:
    sign = "+" if stock["pct_change"] >= 0 else ""
    line = f"- {stock['ticker']}: ${stock['price']:.2f} ({sign}{stock['pct_change']:.1f}%)"
    if stock.get("material_news"):
        line += f" — {stock['material_news']}"
    return line


def _weather_line(weather: dict[str, Any]) -> str:
    precip = weather.get("precip_probability")
    precip_text = f", {precip}% precip" if precip and precip >= 30 else ""
    return (
        f"🌤️ {weather['current_temp_f']}°F, {weather['conditions']}, "
        f"high {weather['high_f']}°/low {weather['low_f']}°{precip_text}. "
        f"{weather['what_to_wear']}"
    )


def _fallback_headsups(
    calendar_events: list[dict[str, Any]] | None,
    emails: list[dict[str, Any]] | None,
    source_failures: dict[str, str],
) -> list[str]:
    heads: list[str] = []
    if calendar_events:
        heads.extend(detect_calendar_headsups(calendar_events))
    if emails:
        for email in emails[:2]:
            subject = email.get("subject", "")
            if any(term in subject.lower() for term in ["due", "deadline", "appointment", "school", "travel"]):
                heads.append(f"Email needs attention: {subject}")
    if source_failures.get("calendar"):
        heads.append("Calendar source needs attention before production runs.")
    return list(dict.fromkeys(heads))[:3]


def compose_brief(
    target_date: date,
    calendar_events: list[dict[str, Any]] | None,
    emails: list[dict[str, Any]] | None,
    weather: dict[str, Any] | None,
    stocks: list[dict[str, Any]] | None,
    source_failures: dict[str, str] | None = None,
) -> str:
    source_failures = source_failures or {}
    lines: list[str] = [
        f"Morning brief for {target_date.strftime('%A, %B %d, %Y')}",
        SEPARATOR,
        "",
        "Good morning! ☀️",
        "",
    ]

    if source_failures.get("calendar"):
        lines.append("📅 Calendar unavailable")
    elif calendar_events:
        lines.append("📅 Today")
        for event in calendar_events:
            lines.append(_format_event(event))
    else:
        lines.append("📅 Today: no scheduled events")
    lines.append("")

    if source_failures.get("gmail"):
        lines.append("📧 Email unavailable")
    elif emails:
        count = len(emails)
        noun = "needs" if count == 1 else "need"
        lines.append(f"📧 Email ({count} {noun} attention)")
        for email in emails:
            lines.append(_format_email(email))
    else:
        lines.append("📧 Email: nothing urgent")
    lines.append("")

    if weather:
        lines.append(_weather_line(weather))
        lines.append("")

    if stocks:
        lines.append("📈 Stocks")
        for stock in stocks:
            lines.append(_format_stock(stock))
        lines.append("")

    heads = _fallback_headsups(calendar_events, emails, source_failures)
    if heads:
        lines.append("⚡ Heads up")
        for item in heads:
            lines.append(f"- {item}")

    return "\n".join(lines).rstrip() + "\n"
