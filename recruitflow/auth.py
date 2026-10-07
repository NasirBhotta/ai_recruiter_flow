"""
Google OAuth 2.0 Authentication Module for Personal Google Accounts.

IMPORTANT ARCHITECTURAL & SECURITY NOTES:
1. Personal Google Accounts (@gmail.com):
   - Service accounts CANNOT access personal Gmail accounts. Service accounts only
     work with Google Workspace business domains that configure Domain-Wide Delegation.
   - For personal accounts, OAuth 2.0 InstalledAppFlow (Desktop Client) is mandatory.
2. Consent Screen Testing Mode:
   - When a Google Cloud project OAuth consent screen is in 'Testing' status,
     refresh tokens expire every 7 days.
   - Any testing user account must be explicitly added to the 'Test Users' list in GCP.
3. Security & Least Privilege:
   - Only requested scopes: gmail.readonly, gmail.send, spreadsheets.
   - Never prompt for Google account passwords.
   - credentials.json and token.json are gitignored.
"""

from __future__ import annotations

import os
from pathlib import Path
import logging
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]


class AuthError(Exception):
    """Raised when authentication setup or refresh fails."""
    pass


def get_google_credentials(
    client_secrets_path: str | Path,
    token_path: str | Path,
    interactive: bool = True,
) -> Credentials | None:
    """
    Load or acquire Google OAuth 2.0 desktop client credentials.

    Args:
        client_secrets_path: Path to credentials.json downloaded from GCP.
        token_path: Path to token.json storing authorized user tokens.
        interactive: Whether to open a browser window if user consent is needed.

    Returns:
        google.oauth2.credentials.Credentials or raises AuthError.
    """
    client_secrets_path = Path(client_secrets_path)
    token_path = Path(token_path)

    creds: Credentials | None = None

    # 1. Attempt to load existing cached token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            logger.info("Loaded cached Google OAuth credentials from token.json.")
        except Exception as e:
            logger.warning(f"Failed to read existing token file: {e}. Re-authenticating.")
            creds = None

    # 2. Check validity and refresh if expired
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            logger.info("Cached Google token expired. Refreshing token via Google OAuth endpoint...")
            creds.refresh(Request())
            # Save refreshed token
            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
            logger.info("Successfully refreshed and updated token.json.")
            return creds
        except Exception as e:
            logger.warning(f"Token refresh failed: {e}. Needs interactive re-authentication.")
            creds = None

    # 3. Interactive OAuth Desktop Flow
    if not client_secrets_path.exists():
        raise AuthError(
            f"OAuth Client Secrets file not found at: {client_secrets_path}.\n"
            "Please create an OAuth 2.0 Desktop Client ID in Google Cloud Console, "
            "download credentials.json to this directory, or run in DEMO_MODE=true."
        )

    if not interactive:
        raise AuthError(
            "Valid Google OAuth token is required, but non-interactive execution was requested."
        )

    logger.info("Starting local OAuth consent flow in default browser...")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets_path), scopes=SCOPES
        )
        # Runs local loopback webserver on an available port
        creds = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
        )
        # Save token for subsequent runs
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
        logger.info(f"OAuth flow complete. Saved authorization token to {token_path}.")
        return creds
    except Exception as e:
        raise AuthError(f"OAuth Desktop Flow failed: {e}") from e


def check_auth_status(
    client_secrets_path: str | Path, token_path: str | Path
) -> dict[str, Any]:
    """Check configuration and health of Google OAuth credentials."""
    cs_path = Path(client_secrets_path)
    tk_path = Path(token_path)

    status: dict[str, Any] = {
        "client_secrets_exists": cs_path.exists(),
        "token_exists": tk_path.exists(),
        "is_valid": False,
        "is_expired": False,
        "scopes": [],
        "message": "",
    }

    if not cs_path.exists():
        status["message"] = f"Missing {cs_path.name}. Real Google operations disabled."
        return status

    if not tk_path.exists():
        status["message"] = f"Missing {tk_path.name}. User must authenticate once."
        return status

    try:
        creds = Credentials.from_authorized_user_file(str(tk_path), SCOPES)
        status["is_valid"] = creds.valid
        status["is_expired"] = creds.expired
        status["scopes"] = list(creds.scopes) if creds.scopes else []
        if creds.valid:
            status["message"] = "Authenticated & active."
        elif creds.expired and creds.refresh_token:
            status["message"] = "Token expired; refreshable."
        else:
            status["message"] = "Token invalid; re-authentication needed."
    except Exception as e:
        status["message"] = f"Corrupted token: {e}"

    return status
