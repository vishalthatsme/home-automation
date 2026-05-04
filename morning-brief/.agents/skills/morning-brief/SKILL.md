---
name: morning-brief
description: Build, run, debug, and maintain the local macOS family morning briefing automation. Use this when asked to generate, test, fix, or schedule the morning brief.
---

# Morning Brief Skill

This skill is for maintaining the local deterministic Python app in ~/HomeAI/automation/morning-brief.

Do not use Codex plugins, Claude MCP, ChatGPT connectors, or Codex automations as runtime dependencies.

Workflow:
1. Read preferences.md.
2. Gather inputs:
   - Gmail via Gmail API
   - Google Calendar via Calendar API
   - Google Calendar browser fallback via local Chrome if API fails
   - Weather via weather.py / Open-Meteo
   - Stocks via stocks.py / yfinance
3. Compose a concise family-facing brief.
4. Read the existing Apple Note.
5. Parse existing brief sections.
6. Archive sections older than the retention window.
7. Prepend today's section.
8. Write back to Apple Notes.
9. Print a confirmation including:
   - timestamp
   - sections included
   - sources that failed
   - archive count
   - fallback path if Notes write failed

Existing project handling:
- Inspect any existing Claude attempt files first.
- Back up the existing directory before destructive changes.
- Preserve useful user preferences and working code.
- Rebuild cleanly.

Calendar source policy:
- Production default is CALENDAR_SOURCE=auto.
- Try official Google Calendar API first.
- If the API fails, use local Chrome browser automation fallback.
- This browser fallback was previously verified in Codex by reading the signed-in Google Calendar through local Chrome after bypassing the broken Codex Google Calendar connector prompt.
- Do not use the broken Codex Google Calendar connector prompt as a dependency.
- Browser mode is read-only and must never modify calendar data.

Gmail source policy:
- Production default is GMAIL_SOURCE=auto.
- Try official Gmail API first.
- If the API fails, use local Chrome browser automation fallback.
- Browser mode is read-only and must never open or modify messages.
- Extract sender + subject only for the final brief; snippets are only for deterministic local scoring.
- Only consider unread Primary emails, collapse duplicate topics, and suppress emails already shown in previous days' briefs.

Graceful degradation:
- Gmail fails: include "📧 Email unavailable"
- Calendar fails: include "📅 Calendar unavailable"
- Weather fails: skip weather silently
- Stocks fail: skip stocks silently
- Notes write fails: write to out/YYYY-MM-DD.md and print clear macOS Automation permission instructions

Required test commands:
- .venv/bin/python brief.py --dry-run
- .venv/bin/python -m compileall .
