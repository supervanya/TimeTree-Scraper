"""Installed-app OAuth for Google Calendar."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
)
DEFAULT_CREDENTIALS_PATH = Path(".state/google-credentials.json")
DEFAULT_TOKEN_PATH = Path(".state/google-token.json")


class GoogleAuthError(RuntimeError):
    """Raised when Google OAuth credentials are missing or invalid."""


def _validate_client_credentials(path: Path) -> None:
    if not path.is_file():
        raise GoogleAuthError(f"Google OAuth credentials were not found: {path}")
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleAuthError(f"Google OAuth credentials are not valid JSON: {path}") from exc
    if "installed" not in payload:
        raise GoogleAuthError("Google OAuth credentials must be for a Desktop app")


def authorize(
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
) -> Credentials:
    """Run interactive OAuth and save a refreshable local token."""

    credentials_path = credentials_path.expanduser().resolve()
    token_path = token_path.expanduser().resolve()
    _validate_client_credentials(credentials_path)
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    credentials = flow.run_local_server(
        port=0,
        prompt="consent",
        authorization_prompt_message="Opening Google authorization in your browser...",
        success_message="Google authorization complete. You may close this tab.",
    )
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json())
    os.chmod(token_path, 0o600)
    return credentials


def load_credentials(
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
    *,
    interactive: bool = False,
) -> Credentials:
    """Load, refresh, or interactively create Google OAuth credentials."""

    token_path = token_path.expanduser().resolve()
    credentials = None
    if token_path.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except (OSError, ValueError) as exc:
            raise GoogleAuthError(f"Google OAuth token is invalid: {token_path}") from exc

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json())
        os.chmod(token_path, 0o600)
    if credentials and credentials.valid:
        return credentials
    if interactive:
        return authorize(credentials_path, token_path)
    raise GoogleAuthError("Google is not authorized. Run `timetree-sync google-auth` first.")


def calendar_service(credentials: Credentials) -> Any:
    """Build an authenticated Google Calendar API client."""

    return build("calendar", "v3", credentials=credentials, cache_discovery=False)
