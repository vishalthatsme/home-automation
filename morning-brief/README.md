# morning-brief

Local macOS Python automation that builds a concise family morning briefing and prepends it to the Apple Note titled `Family Morning Briefing`.

## Existing Files

If `~/HomeAI/automation/morning-brief` existed before this rebuild, it was backed up to `~/HomeAI/automation/morning-brief-backup-<YYYYMMDD-HHMMSS>/`. Review that backup if needed.

## Setup

```bash
cd ~/HomeAI/automation/morning-brief
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

If `/usr/bin/python3` is older than Python 3.11, create the venv with a newer local Python instead.

## Google API Setup

1. Create Google Cloud OAuth Desktop credentials.
2. Enable Gmail API and Google Calendar API.
3. Save the OAuth desktop credentials as `credentials.json` in this directory.
4. First API run creates `token.json`.

The app uses only read-only scopes:
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/calendar.readonly`

## Environment

```bash
cp .env.example .env
```

`OPENAI_API_KEY` is optional. Recommended production setting:

```bash
CALENDAR_SOURCE=auto
GMAIL_SOURCE=auto
```

## Calendar Setup Options

### Option A: Preferred Google Calendar API

```bash
.venv/bin/python brief.py --dry-run --calendar-source api
```

Complete OAuth in the browser when prompted.

### Option B: Local Chrome Browser Fallback

Use this if Calendar API is not working yet.

1. Open Chrome.
2. Sign into Google Calendar.
3. Confirm that `calendar.google.com` loads the correct calendar.
4. Run:

```bash
.venv/bin/python brief.py --dry-run --calendar-source browser --calendar-debug-screenshot
```

The Playwright fallback is read-only. It can connect to a Chrome DevTools session on port `9222`, or use a local ignored copy of the signed-in Chrome profile.

## Gmail Setup Options

### Option A: Preferred Gmail API

```bash
.venv/bin/python brief.py --dry-run --gmail-source api
```

### Option B: Local Chrome Browser Fallback

```bash
.venv/bin/python brief.py --dry-run --gmail-source browser --gmail-debug-screenshot
```

Browser mode is read-only. It parses Gmail search-result rows for sender, subject, labels, snippets, and times without opening messages.

Email filtering is intentionally conservative:
- Gmail search is restricted to unread `category:primary`.
- Duplicate reminders about the same topic are collapsed.
- Marketing and real-estate alert noise is suppressed.
- Emails already included in previous days' Apple Notes briefs are not repeated.

## First Dry Run

```bash
.venv/bin/python brief.py --dry-run --verbose
```

## First Apple Notes Write

```bash
.venv/bin/python brief.py
```

Approve macOS Notes Automation permission if prompted.

## Install launchd

```bash
cp launchd/com.vishal.morningbrief.plist ~/Library/LaunchAgents/
launchctl bootout "gui/$UID" ~/Library/LaunchAgents/com.vishal.morningbrief.plist 2>/dev/null || true
launchctl bootstrap "gui/$UID" ~/Library/LaunchAgents/com.vishal.morningbrief.plist
launchctl enable "gui/$UID/com.vishal.morningbrief"
launchctl kickstart -k "gui/$UID/com.vishal.morningbrief"
```

Check:

```bash
tail -100 log/stdout.log
tail -100 log/stderr.log
```

## Troubleshooting

- If Gmail or Calendar API auth fails, delete `token.json` and retry.
- If Notes write fails, check System Settings -> Privacy & Security -> Automation and allow Terminal/Python/osascript to control Notes.
- If browser calendar fallback fails, sign into Google Calendar in Chrome and retry with `--calendar-debug-screenshot`.
- If browser Gmail fallback fails, sign into Gmail in Chrome and retry with `--gmail-debug-screenshot`.
- If yfinance fails, the stocks section is skipped silently.
