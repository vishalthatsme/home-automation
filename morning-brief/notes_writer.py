from __future__ import annotations

import html
import re
import subprocess
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from dateutil import parser as dateparser

from config import LOCAL_TZ, LOG_DIR

HEADER_RE = re.compile(r"^Morning brief for (?P<date>.+)$", re.MULTILINE)


class NotesWriterError(RuntimeError):
    pass


def _automation_help() -> str:
    return (
        "System Settings -> Privacy & Security -> Automation, allow "
        "Terminal/Python/osascript to control Notes."
    )


def _quote_applescript(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_osascript(script: str, timeout: int = 60) -> str:
    result = subprocess.run(
        ["osascript", "-"],
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode == 0:
        return result.stdout
    stderr = result.stderr.strip() or result.stdout.strip()
    lower = stderr.lower()
    if "not allowed" in lower or "not authorized" in lower or "denied" in lower:
        raise PermissionError(f"macOS denied Notes automation. {_automation_help()}")
    if "NOTE_NOT_FOUND" in stderr:
        raise FileNotFoundError("Apple Note not found.")
    if "MULTIPLE_NOTES" in stderr:
        raise NotesWriterError("Multiple Apple Notes matched the target title; refusing to write.")
    raise NotesWriterError(f"osascript failed: {stderr}")


def _note_script(title: str, action: str) -> str:
    title_literal = _quote_applescript(title)
    return f"""
set noteTitle to {title_literal}
tell application "Notes"
    set matches to every note whose name is noteTitle
    if (count of matches) is 0 then error "NOTE_NOT_FOUND"
    if (count of matches) is greater than 1 then error "MULTIPLE_NOTES"
    set theNote to item 1 of matches
    {action}
end tell
"""


def read_note(title: str) -> str:
    return _run_osascript(_note_script(title, "return plaintext of theNote")).strip()


def _text_to_notes_html(body: str) -> str:
    parts = []
    for line in body.splitlines():
        if line == "":
            parts.append("<div><br></div>")
        else:
            parts.append(f"<div>{html.escape(line)}</div>")
    return "\n".join(parts)


def strip_note_title(title: str, body: str) -> str:
    lines = body.splitlines()
    if lines and lines[0].strip() == title:
        return "\n".join(lines[1:]).lstrip("\n")
    return body


def write_note(title: str, body: str) -> None:
    clean_body = strip_note_title(title, body)
    notes_html = f"<h1>{html.escape(title)}</h1>\n" + _text_to_notes_html(clean_body)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".html", delete=False) as tmp:
        tmp.write(notes_html)
        tmp_path = tmp.name
    try:
        action = f'set body of theNote to (read POSIX file {_quote_applescript(tmp_path)} as «class utf8»)'
        _run_osascript(_note_script(title, action), timeout=90)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_header_date(value: str) -> date | None:
    try:
        return dateparser.parse(value, fuzzy=False).date()
    except Exception:
        return None


def parse_briefs(body: str) -> list[tuple[date | None, str]]:
    matches = list(HEADER_RE.finditer(body))
    if not matches:
        return [(None, body.strip())] if body.strip() else []

    sections: list[tuple[date | None, str]] = []
    if matches[0].start() > 0:
        prefix = body[: matches[0].start()].strip()
        if prefix:
            sections.append((None, prefix))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        text = body[match.start() : end].strip()
        sections.append((_parse_header_date(match.group("date")), text))
    return sections


def compose_body(briefs: list[tuple[date | None, str]]) -> str:
    return "\n\n".join(text.strip() for _, text in briefs if text.strip()).rstrip() + "\n"


def archive_old_briefs(
    briefs: list[tuple[date | None, str]], retention_days: int
) -> tuple[list[tuple[date | None, str]], list[tuple[date | None, str]]]:
    cutoff = datetime.now(LOCAL_TZ).date() - timedelta(days=retention_days)
    kept: list[tuple[date | None, str]] = []
    archived: list[tuple[date | None, str]] = []
    for brief_date, text in briefs:
        if brief_date is None or brief_date >= cutoff:
            kept.append((brief_date, text))
        else:
            archived.append((brief_date, text))
    return kept, archived


def write_archives(archived: list[tuple[date | None, str]], log_dir: Path = LOG_DIR) -> int:
    by_month: dict[str, list[str]] = {}
    for brief_date, text in archived:
        if brief_date is None:
            continue
        by_month.setdefault(brief_date.strftime("%Y-%m"), []).append(text.strip())

    log_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for month, sections in by_month.items():
        archive_path = log_dir / f"{month}.md"
        existing = archive_path.read_text(encoding="utf-8") if archive_path.exists() else ""
        addition = "\n\n".join(sections).strip()
        if existing.strip():
            archive_path.write_text(existing.rstrip() + "\n\n" + addition + "\n", encoding="utf-8")
        else:
            archive_path.write_text(addition + "\n", encoding="utf-8")
        count += len(sections)
    return count


def prepend_to_note(title: str, new_section: str) -> None:
    current = strip_note_title(title, read_note(title))
    new_sections = parse_briefs(new_section)
    new_date = new_sections[0][0] if new_sections else None
    existing = parse_briefs(current)
    if new_date:
        existing = [(brief_date, text) for brief_date, text in existing if brief_date != new_date]
    write_note(title, compose_body([(new_date, new_section.strip()), *existing]))


if __name__ == "__main__":
    print(f"Read {len(read_note('Family Morning Briefing'))} characters.")
