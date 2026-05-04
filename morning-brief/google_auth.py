from __future__ import annotations

from pathlib import Path

from google.auth.exceptions import GoogleAuthError as BaseGoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import APP_DIR

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GoogleAuthError(RuntimeError):
    pass


def _credentials_path() -> Path:
    return APP_DIR / "credentials.json"


def _token_path() -> Path:
    return APP_DIR / "token.json"


def get_credentials() -> Credentials:
    credentials_file = _credentials_path()
    token_file = _token_path()

    if not credentials_file.exists():
        raise GoogleAuthError(
            "Missing credentials.json. Create Google Cloud OAuth Desktop credentials, "
            "enable Gmail API and Google Calendar API, then save the file as "
            f"{credentials_file}."
        )

    creds: Credentials | None = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as exc:
            raise GoogleAuthError(
                "token.json exists but could not be read. Delete token.json and retry."
            ) from exc

    try:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds
    except BaseGoogleAuthError as exc:
        raise GoogleAuthError("Google OAuth failed. Delete token.json and retry.") from exc
    except Exception as exc:
        raise GoogleAuthError(f"Google OAuth failed: {exc}") from exc


def build_service(api_name: str, api_version: str):
    try:
        return build(api_name, api_version, credentials=get_credentials(), cache_discovery=False)
    except GoogleAuthError:
        raise
    except Exception as exc:
        raise GoogleAuthError(f"Could not build Google {api_name} service: {exc}") from exc


def gmail_service():
    return build_service("gmail", "v1")


def calendar_service():
    return build_service("calendar", "v3")
