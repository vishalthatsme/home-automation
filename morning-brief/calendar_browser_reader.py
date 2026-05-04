from __future__ import annotations

import os
import re
import socket
import subprocess
import time as time_module
import urllib.request
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from dateutil import parser as dateparser

from config import GOOGLE_CALENDAR_URL, LOCAL_TZ, OUT_DIR


class CalendarBrowserError(RuntimeError):
    pass


EVENT_RE = re.compile(
    r"(?P<start>(?:All day)|(?:\d{1,2}(?::\d{2})?\s?(?:am|pm)))"
    r"(?:\s*(?:to|–|-)\s*(?P<end>\d{1,2}(?::\d{2})?\s?(?:am|pm)))?"
    r",\s*(?P<title>.*?),\s*(?:Personal Gmail|Calendar:)",
    re.IGNORECASE,
)


def _target_url(target_date: date) -> str:
    base = GOOGLE_CALENDAR_URL.rstrip("/")
    return f"{base}/{target_date.year}/{target_date.month}/{target_date.day}"


def _parse_time(target_date: date, raw: str | None) -> datetime | None:
    if not raw or raw.lower() == "all day":
        return None
    parsed = dateparser.parse(f"{target_date.isoformat()} {raw}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


def _copy_chrome_profile(source: Path, target: Path) -> None:
    """Copy enough of Chrome's local profile for read-only Calendar fallback.

    The copy lives under out/ and is ignored by git. It may contain local browser
    cookies, so it must never be logged, committed, or moved off this Mac.
    """
    excludes = [
        "--exclude=Singleton*",
        "--exclude=*/Cache",
        "--exclude=*/Code Cache",
        "--exclude=*/GPUCache",
        "--exclude=*/DawnCache",
        "--exclude=*/GrShaderCache",
        "--exclude=*/ShaderCache",
        "--exclude=*/Crashpad",
        "--exclude=Safe Browsing",
        "--exclude=BrowserMetrics",
        "--exclude=Crashpad",
        "--exclude=GrShaderCache",
        "--exclude=ShaderCache",
        "--exclude=*/Safe Browsing*",
        "--exclude=*/OptimizationHints",
        "--exclude=*/component_crx_cache",
        "--exclude=*/BrowserMetrics*",
        "--exclude=*/File System",
        "--exclude=*/Storage",
        "--exclude=*/Service Worker/CacheStorage",
        "--exclude=*/Service Worker/ScriptCache",
        "--exclude=*/IndexedDB",
        "--exclude=*/blob_storage",
        "--exclude=*/Media Cache",
    ]
    target.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-a", "--delete", *excludes, f"{source}/", f"{target}/"]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    for lock_file in target.glob("Singleton*"):
        lock_file.unlink(missing_ok=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_cdp(port: int) -> None:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1):
                return
        except Exception as exc:
            last_error = exc
            time_module.sleep(0.5)
    raise CalendarBrowserError(f"Chrome DevTools port {port} did not become available: {last_error}")


def _event_from_label(label: str, target_date: date) -> dict[str, Any] | None:
    if target_date.strftime("%B %-d, %Y") not in label and target_date.strftime("%B %d, %Y") not in label:
        return None
    match = EVENT_RE.search(label)
    if not match:
        return None
    title = match.group("title").strip()
    location = None
    location_match = re.search(r"Location:\s*(.*?)(?:,\s*May|$)", label)
    if location_match:
        location = location_match.group(1).strip() or None
    return {
        "title": title,
        "start": _parse_time(target_date, match.group("start")),
        "end": _parse_time(target_date, match.group("end")),
        "location": location,
        "attendees": [],
        "description_excerpt": None,
        "source": "google_calendar_browser",
    }


def _extract_with_page(page, target_date: date, debug_screenshot: bool) -> list[dict[str, Any]]:
    page.goto(_target_url(target_date), wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(5000)
    title = page.title()
    url = page.url
    if debug_screenshot:
        page.screenshot(
            path=str(OUT_DIR / f"calendar-debug-{target_date.isoformat()}.png"),
            full_page=True,
            timeout=15000,
        )
    if "accounts.google.com" in url or "Sign in" in title:
        raise CalendarBrowserError(
            "Google Calendar browser fallback failed because Chrome is not signed in or the session is unavailable. Open Chrome, sign into Google Calendar, then retry."
        )
    labels = page.locator("button, [aria-label]").evaluate_all(
        """els => els.map(el => el.getAttribute('aria-label') || el.innerText || '').filter(Boolean)"""
    )
    try:
        body_text = page.locator("body").inner_text(timeout=10000)
        labels.extend(line.strip() for line in body_text.splitlines() if line.strip())
    except Exception:
        pass
    events = []
    seen: set[tuple[str, str]] = set()
    for label in labels:
        event = _event_from_label(label, target_date)
        if not event:
            continue
        key = (event["title"], event["start"].isoformat() if event["start"] else "all-day")
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    events.sort(key=lambda event: event["start"] or datetime.combine(target_date, time.min, tzinfo=LOCAL_TZ))
    return events


def _extract_via_external_chrome(p, chrome_path: Path, profile_dir: Path, target_date: date, debug_screenshot: bool) -> list[dict[str, Any]]:
    port = int(os.getenv("CHROME_FALLBACK_PORT", "0")) or _free_port()
    process = subprocess.Popen(
        [
            str(chrome_path),
            f"--user-data-dir={profile_dir}",
            "--profile-directory=Default",
            f"--remote-debugging-port={port}",
            _target_url(target_date),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_cdp(port)
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=5000)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        try:
            return _extract_with_page(page, target_date, debug_screenshot)
        finally:
            page.close()
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def fetch_calendar_events_browser(target_date: date, debug_screenshot: bool = False) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise CalendarBrowserError("Playwright is not installed. Run .venv/bin/pip install -r requirements.txt.") from exc

    async_error = None
    try:
        with sync_playwright() as p:
            cdp_url = os.getenv("CHROME_CDP_URL", "http://127.0.0.1:9222")
            try:
                browser = p.chromium.connect_over_cdp(cdp_url, timeout=2000)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
                try:
                    return _extract_with_page(page, target_date, debug_screenshot)
                finally:
                    page.close()
                    browser.close()
            except Exception as exc:
                async_error = exc

            chrome_path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            user_data_dir = Path(os.path.expanduser("~/Library/Application Support/Google/Chrome"))
            if not chrome_path.exists():
                raise CalendarBrowserError("Google Chrome was not found in /Applications.")
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    executable_path=str(chrome_path),
                    headless=False,
                    args=["--profile-directory=Default"],
                    ignore_default_args=["--use-mock-keychain"],
                    timeout=30000,
                )
                page = context.new_page()
                try:
                    return _extract_with_page(page, target_date, debug_screenshot)
                finally:
                    context.close()
            except PlaywrightError:
                copy_dir = OUT_DIR / "chrome-profile-copy-calendar"
                try:
                    _copy_chrome_profile(user_data_dir, copy_dir)
                    return _extract_via_external_chrome(
                        p, chrome_path, copy_dir, target_date, debug_screenshot
                    )
                except Exception as copy_exc:
                    raise CalendarBrowserError(
                        "Google Calendar browser fallback could not attach to Chrome. "
                        "If Chrome is already running, either close Chrome before retrying "
                        "or relaunch Chrome with --remote-debugging-port=9222. "
                        f"Profile-copy fallback failed with: {copy_exc}"
                    ) from copy_exc
    except CalendarBrowserError:
        raise
    except Exception as exc:
        detail = f" Last connection error: {async_error}" if async_error else ""
        raise CalendarBrowserError(f"Google Calendar browser fallback failed gracefully.{detail} {exc}") from exc
