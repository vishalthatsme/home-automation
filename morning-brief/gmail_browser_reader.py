from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from calendar_browser_reader import _copy_chrome_profile, _free_port, _wait_for_cdp
from config import GMAIL_URL, LOCAL_TZ, OUT_DIR
from gmail_reader import filter_rank_emails


class GmailBrowserError(RuntimeError):
    pass


SEARCH_QUERIES = [
    "category:primary is:unread newer_than:24h",
    "category:primary is:unread is:important newer_than:48h",
]


def _search_url(query: str) -> str:
    return f"{GMAIL_URL.rstrip('/')}/#search/{urllib.parse.quote(query)}"


def _clean_text(value: str) -> str:
    value = re.sub(r"[\u034f\u200c\ufeff]+", " ", value)
    value = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
    return value


def _row_to_item(row: str) -> dict[str, Any] | None:
    lines = [_clean_text(line) for line in row.splitlines() if _clean_text(line)]
    if len(lines) < 3:
        return None
    sender = lines[0]
    index = 1
    if index < len(lines) and lines[index].isdigit():
        index += 1
    while index < len(lines) and lines[index] in {"Inbox", "Starred", "Important", "Unread"}:
        index += 1
    if index >= len(lines):
        return None
    subject = lines[index]
    snippet = lines[index + 1] if index + 1 < len(lines) else ""
    labels = [line.upper() for line in lines if line in {"Inbox", "Starred", "Important", "Unread"}]
    return {
        "sender": sender,
        "subject": subject,
        "date": datetime.now(LOCAL_TZ),
        "snippet": snippet[:240],
        "labels": labels,
    }


def _extract_rows(page) -> list[str]:
    return page.locator('tr[role="row"], div[role="main"] tr').evaluate_all(
        """els => els.map(el => el.innerText).filter(Boolean)"""
    )


def _extract_with_page(page, debug_screenshot: bool) -> list[dict[str, Any]]:
    items: dict[tuple[str, str], dict[str, Any]] = {}
    for query in SEARCH_QUERIES:
        page.goto(_search_url(query), wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(7000)
        title = page.title()
        if "accounts.google.com" in page.url or "Sign in" in title:
            raise GmailBrowserError(
                "Gmail browser fallback failed because Chrome is not signed in or the session is unavailable. Open Chrome, sign into Gmail, then retry."
            )
        if debug_screenshot:
            safe_query = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
            page.screenshot(
                path=str(OUT_DIR / f"gmail-debug-{safe_query}.png"),
                full_page=True,
                timeout=15000,
            )
        for row in _extract_rows(page):
            item = _row_to_item(row)
            if not item:
                continue
            key = (item["sender"], item["subject"])
            if key not in items or item["score"] > items[key]["score"]:
                items[key] = item
    return filter_rank_emails(list(items.values()))


def _with_browser(profile_dir: Path, debug_screenshot: bool) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise GmailBrowserError("Playwright is not installed. Run .venv/bin/pip install -r requirements.txt.") from exc

    chrome_path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome_path.exists():
        raise GmailBrowserError("Google Chrome was not found in /Applications.")

    port = int(os.getenv("CHROME_GMAIL_PORT", "0")) or _free_port()
    process = subprocess.Popen(
        [
            str(chrome_path),
            f"--user-data-dir={profile_dir}",
            "--profile-directory=Default",
            f"--remote-debugging-port={port}",
            _search_url(SEARCH_QUERIES[0]),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_cdp(port)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=5000)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            try:
                return _extract_with_page(page, debug_screenshot)
            finally:
                page.close()
                browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def fetch_attention_emails_browser(limit: int = 5, debug_screenshot: bool = False) -> list[dict[str, Any]]:
    user_data_dir = Path(os.path.expanduser("~/Library/Application Support/Google/Chrome"))
    copy_dir = OUT_DIR / "chrome-profile-copy-gmail"
    try:
        _copy_chrome_profile(user_data_dir, copy_dir)
        return _with_browser(copy_dir, debug_screenshot)[:limit]
    except GmailBrowserError:
        raise
    except Exception as exc:
        raise GmailBrowserError(f"Gmail browser fallback failed gracefully: {exc}") from exc
