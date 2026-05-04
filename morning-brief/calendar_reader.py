from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from dateutil import parser as dateparser

from config import LOCAL_TZ
from google_auth import GoogleAuthError, calendar_service


class CalendarAPIError(RuntimeError):
    pass


HEADS_UP_TERMS = [
    "doctor",
    "dentist",
    "pediatric",
    "school",
    "daycare",
    "teacher",
    "staff",
    "kid",
    "jo ",
    "soccer",
    "rsm",
    "travel",
    "flight",
    "birthday",
]


def _parse_event_dt(value: dict[str, str], is_end: bool = False) -> datetime:
    if "dateTime" in value:
        return dateparser.parse(value["dateTime"]).astimezone(LOCAL_TZ)
    parsed_date = date.fromisoformat(value["date"])
    if is_end:
        parsed_date = parsed_date - timedelta(days=1)
        return datetime.combine(parsed_date, time(23, 59), tzinfo=LOCAL_TZ)
    return datetime.combine(parsed_date, time.min, tzinfo=LOCAL_TZ)


def _declined_by_self(event: dict[str, Any]) -> bool:
    for attendee in event.get("attendees", []):
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return True
    return False


def fetch_calendar_events(target_date: date) -> list[dict[str, Any]]:
    start = datetime.combine(target_date, time.min, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    try:
        service = calendar_service()
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            )
            .execute()
        )
        events = []
        for event in result.get("items", []):
            if event.get("status") == "cancelled" or _declined_by_self(event):
                continue
            start_dt = _parse_event_dt(event["start"])
            end_dt = _parse_event_dt(event["end"], is_end=True)
            attendees = [
                attendee.get("email", "")
                for attendee in event.get("attendees", [])
                if attendee.get("email")
            ]
            description = (event.get("description") or "").strip()
            events.append(
                {
                    "title": event.get("summary", "(untitled)"),
                    "start": start_dt,
                    "end": end_dt,
                    "location": event.get("location") or None,
                    "attendees": attendees,
                    "description_excerpt": description[:240] if description else None,
                    "source": "google_calendar_api",
                }
            )
        return events
    except GoogleAuthError as exc:
        raise CalendarAPIError(str(exc)) from exc
    except Exception as exc:
        raise CalendarAPIError(f"Google Calendar API read failed: {exc}") from exc


def format_event_time(event: dict[str, Any]) -> str:
    start = event.get("start")
    end = event.get("end")
    if not isinstance(start, datetime):
        return "Time TBD"
    if start.time() == time.min and isinstance(end, datetime) and end.time().hour == 23:
        return "All day"
    start_text = start.strftime("%-I:%M%p").lower().replace(":00", "")
    if not isinstance(end, datetime):
        return start_text
    end_text = end.strftime("%-I:%M%p").lower().replace(":00", "")
    return f"{start_text}-{end_text}"


def detect_calendar_headsups(events: list[dict[str, Any]]) -> list[str]:
    heads: list[str] = []
    timed_events = [event for event in events if isinstance(event.get("start"), datetime)]
    for event in timed_events:
        title = event.get("title", "")
        location = event.get("location")
        start = event["start"]
        text = f"{title} {location or ''}".lower()
        if start.time() < time(8, 0):
            heads.append(f"Early start: {format_event_time(event)} {title}")
        if location:
            heads.append(f"Travel/location: {title} at {location}")
        if any(term in text for term in HEADS_UP_TERMS):
            heads.append(f"Family/logistics: {title}")

    sorted_events = sorted(timed_events, key=lambda event: event["start"])
    for prev, current in zip(sorted_events, sorted_events[1:]):
        if isinstance(prev.get("end"), datetime) and current["start"] < prev["end"]:
            heads.append(f"Calendar overlap: {prev.get('title')} and {current.get('title')}")
    return list(dict.fromkeys(heads))[:4]
