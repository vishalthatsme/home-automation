This repository builds a deterministic local macOS morning briefing automation.

Rules for Codex:
- Prefer small, testable Python modules.
- Do not rely on Codex plugins, Claude MCP, Claude Desktop, ChatGPT connectors, or Codex automations at runtime.
- Runtime integrations must use official APIs or deterministic local commands.
- Preserve user privacy.
- Do not print full email bodies in normal logs.
- Never commit credentials.json, token.json, .env, logs, generated output, or generated archives.
- Always support --dry-run.
- Always degrade gracefully when one source fails.
- If Apple Notes writing fails, write the brief to out/YYYY-MM-DD.md and print clear recovery instructions.
- Use America/Los_Angeles as the local timezone.
- Use absolute paths in launchd.
- Before declaring done, run:
  .venv/bin/python brief.py --dry-run
  .venv/bin/python -m compileall .
- Show the dry-run output.

Existing project handling:
- If ~/HomeAI/automation/morning-brief already exists, inspect it first.
- Back it up to ~/HomeAI/automation/morning-brief-backup-<YYYYMMDD-HHMMSS>/ before making destructive changes.
- Preserve useful preferences and working code.
- Do not trust the previous Claude code without verification.
- Rebuild cleanly rather than making a fragile patchwork.

Calendar integration note:
The Codex Google Calendar connector prompt was broken. A working workaround was verified in Codex by reading the user's signed-in Google Calendar through local Chrome browser automation. The page successfully loaded:
"Google Calendar - Schedule starting Saturday, May 2, 2026."

Runtime policy for calendar:
- Prefer official Google Calendar API for production.
- If API auth fails, fallback to calendar_browser_reader.py.
- Do not use Codex Google Calendar connector prompts at runtime.
- Browser automation must be read-only.
- Browser automation must not create, edit, delete, accept, or decline events.
- If browser automation fails, include "📅 Calendar unavailable" and continue.

Runtime policy for Gmail:
- Prefer official Gmail API for production.
- If API auth fails, fallback to gmail_browser_reader.py.
- Browser automation must be read-only.
- Browser automation must not open, send, archive, delete, label, or otherwise modify messages.
- Browser mode should extract sender, subject, labels, snippet, and timestamp only; never full email bodies.
- Email filtering must be Primary-only, unread-only, deduplicated by topic, and should not repeat emails from previous days' briefs.
