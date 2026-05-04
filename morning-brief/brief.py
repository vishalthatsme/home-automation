#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from brief_model import compose_brief
from calendar_browser_reader import CalendarBrowserError, fetch_calendar_events_browser
from calendar_reader import CalendarAPIError, fetch_calendar_events
from config import (
    CALENDAR_SOURCE,
    DEFAULT_RETENTION_DAYS,
    GMAIL_SOURCE,
    LOCAL_TZ,
    NOTE_TITLE,
    OUT_DIR,
)
from gmail_browser_reader import GmailBrowserError, fetch_attention_emails_browser
from gmail_reader import (
    GmailReaderError,
    extract_reported_email_keys,
    filter_rank_emails,
    fetch_attention_emails,
)
from notes_writer import (
    archive_old_briefs,
    compose_body,
    parse_briefs,
    read_note,
    strip_note_title,
    write_archives,
    write_note,
)
from stocks import get_stocks
from weather import get_weather


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and publish the family morning brief.")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated brief and do not write Notes.")
    parser.add_argument("--no-archive", action="store_true", help="Skip archival/pruning.")
    parser.add_argument("--date", help="Generate for a specific date, YYYY-MM-DD.")
    parser.add_argument("--output-md", action="store_true", help="Write out/YYYY-MM-DD.md.")
    parser.add_argument("--verbose", action="store_true", help="Print extra diagnostics without email bodies.")
    parser.add_argument("--calendar-source", choices=["auto", "api", "browser"], default=None)
    parser.add_argument("--gmail-source", choices=["auto", "api", "browser"], default=None)
    parser.add_argument("--calendar-debug-screenshot", action="store_true")
    parser.add_argument("--gmail-debug-screenshot", action="store_true")
    return parser.parse_args()


def _target_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(LOCAL_TZ).date()


def _read_calendar(
    target: date, source: str, debug_screenshot: bool
) -> tuple[list[dict] | None, str | None, dict[str, str]]:
    failures: dict[str, str] = {}
    if source == "api":
        try:
            return fetch_calendar_events(target), "google_calendar_api", failures
        except CalendarAPIError as exc:
            failures["calendar"] = str(exc)
            return None, None, failures
    if source == "browser":
        try:
            return fetch_calendar_events_browser(target, debug_screenshot), "google_calendar_browser", failures
        except CalendarBrowserError as exc:
            failures["calendar"] = str(exc)
            return None, None, failures

    try:
        return fetch_calendar_events(target), "google_calendar_api", failures
    except CalendarAPIError as api_exc:
        failures["calendar_api"] = str(api_exc)
        try:
            return fetch_calendar_events_browser(target, debug_screenshot), "google_calendar_browser", failures
        except CalendarBrowserError as browser_exc:
            failures["calendar_browser"] = str(browser_exc)
            failures["calendar"] = f"API failed; browser fallback failed: {browser_exc}"
            return None, None, failures


def _read_gmail(
    source: str, debug_screenshot: bool
) -> tuple[list[dict] | None, str | None, dict[str, str]]:
    failures: dict[str, str] = {}
    if source == "api":
        try:
            return fetch_attention_emails(), "gmail_api", failures
        except GmailReaderError as exc:
            failures["gmail"] = str(exc)
            return None, None, failures
    if source == "browser":
        try:
            return fetch_attention_emails_browser(debug_screenshot=debug_screenshot), "gmail_browser", failures
        except GmailBrowserError as exc:
            failures["gmail"] = str(exc)
            return None, None, failures

    try:
        return fetch_attention_emails(), "gmail_api", failures
    except GmailReaderError as api_exc:
        failures["gmail_api"] = str(api_exc)
        try:
            return fetch_attention_emails_browser(debug_screenshot=debug_screenshot), "gmail_browser", failures
        except GmailBrowserError as browser_exc:
            failures["gmail_browser"] = str(browser_exc)
            failures["gmail"] = f"API failed; browser fallback failed: {browser_exc}"
            return None, None, failures


def _write_output(target: date, brief: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{target.isoformat()}.md"
    path.write_text(brief, encoding="utf-8")
    return path


def main() -> int:
    args = _parse_args()
    target = _target_date(args.date)
    calendar_source = (args.calendar_source or CALENDAR_SOURCE or "auto").lower()
    gmail_source = (args.gmail_source or GMAIL_SOURCE or "auto").lower()
    source_status: dict[str, str] = {}
    failures: dict[str, str] = {}
    previous_email_keys: set[str] = set()
    current_body_for_write = ""
    try:
        current_body_for_write = strip_note_title(NOTE_TITLE, read_note(NOTE_TITLE))
        previous_email_keys = extract_reported_email_keys(current_body_for_write, target)
    except Exception as exc:
        if args.verbose:
            failures["notes_read_for_email_memory"] = str(exc)

    emails, gmail_used, gmail_failures = _read_gmail(gmail_source, args.gmail_debug_screenshot)
    if emails:
        emails = filter_rank_emails(emails, previously_reported=previous_email_keys)
    failures.update(gmail_failures)
    source_status["gmail"] = gmail_used or "unavailable"

    calendar_events, calendar_used, calendar_failures = _read_calendar(
        target, calendar_source, args.calendar_debug_screenshot
    )
    failures.update(calendar_failures)
    source_status["calendar"] = calendar_used or "unavailable"

    weather = get_weather()
    source_status["weather"] = "ok" if weather else "skipped"

    stocks = get_stocks()
    source_status["stocks"] = "ok" if stocks else "skipped"

    brief = compose_brief(target, calendar_events, emails, weather, stocks, failures)

    output_path = None
    if args.output_md:
        output_path = _write_output(target, brief)

    if args.dry_run:
        print(brief.rstrip())
        print()
        print("Source status:")
        for name, status in source_status.items():
            print(f"- {name}: {status}")
        if failures and args.verbose:
            print("Failures:")
            for name, error in failures.items():
                print(f"- {name}: {error}")
        if output_path:
            print(f"Markdown written: {output_path}")
        return 0

    archived_count = 0
    try:
        current_body = current_body_for_write or strip_note_title(NOTE_TITLE, read_note(NOTE_TITLE))
        parsed = parse_briefs(current_body)
        parsed = [(brief_date, text) for brief_date, text in parsed if brief_date != target]
        if not args.no_archive:
            parsed, archived = archive_old_briefs(parsed, DEFAULT_RETENTION_DAYS)
            archived_count = write_archives(archived)
        new_body = compose_body([(target, brief.strip()), *parsed])
        write_note(NOTE_TITLE, new_body)
    except Exception as exc:
        fallback_path = _write_output(target, brief)
        print(f"Apple Notes write failed: {exc}", file=sys.stderr)
        print(f"Brief saved to {fallback_path}", file=sys.stderr)
        print(
            "Recovery: System Settings -> Privacy & Security -> Automation, allow Terminal/Python/osascript to control Notes.",
            file=sys.stderr,
        )
        return 1

    print(f"timestamp: {datetime.now(LOCAL_TZ).isoformat(timespec='seconds')}")
    print(f"note: {NOTE_TITLE}")
    print(f"sources: {source_status}")
    print(f"email_items: {len(emails or [])}")
    print(f"calendar_items: {len(calendar_events or [])}")
    print(f"archived_briefs: {archived_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
