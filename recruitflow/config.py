"""
Configuration module for RecruitFlow.
Loads settings from environment variables and .env file.
"""

from __future__ import annotations

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Operational Mode
    demo_mode: bool = Field(default=True, alias="DEMO_MODE")

    # Gemini AI
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    # Google API OAuth
    google_client_secrets_file: str = Field(
        default="credentials.json", alias="GOOGLE_CLIENT_SECRETS_FILE"
    )
    google_token_file: str = Field(
        default="token.json", alias="GOOGLE_TOKEN_FILE"
    )

    # Google Sheets
    spreadsheet_id: str | None = Field(default=None, alias="SPREADSHEET_ID")
    sheet_name: str = Field(default="Candidates", alias="SHEET_NAME")

    # Gmail Intake
    gmail_query: str = Field(
        default='subject:"RecruitFlow Demo" has:attachment newer_than:7d',
        alias="GMAIL_QUERY",
    )
    max_attachment_size_mb: float = Field(
        default=10.0, alias="MAX_ATTACHMENT_SIZE_MB"
    )
    poll_interval_seconds: int = Field(
        default=60, alias="POLL_INTERVAL_SECONDS"
    )

    # Email Dispatch & Safety
    enable_email_send: bool = Field(default=False, alias="ENABLE_EMAIL_SEND")
    demo_recipient_override: str | None = Field(
        default=None, alias="DEMO_RECIPIENT_OVERRIDE"
    )
    scheduling_url: str = Field(
        default="https://calendly.com/recruitflow-demo/interview-30min",
        alias="SCHEDULING_URL",
    )
    sender_name: str = Field(
        default="RecruitFlow Talent Team", alias="SENDER_NAME"
    )

    # Storage Paths
    database_path: str = Field(
        default="data/recruitflow.db", alias="DATABASE_PATH"
    )
    sample_cvs_dir: str = Field(
        default="data/sample_cvs", alias="SAMPLE_CVS_DIR"
    )

    @property
    def db_path_resolved(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def sample_cvs_dir_resolved(self) -> Path:
        path = Path(self.sample_cvs_dir)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def client_secrets_resolved(self) -> Path:
        path = Path(self.google_client_secrets_file)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path

    @property
    def token_file_resolved(self) -> Path:
        path = Path(self.google_token_file)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path


_settings_instance: Settings | None = None


def get_settings(reload: bool = False) -> Settings:
    """Return the singleton Settings instance, optionally reloaded."""
    global _settings_instance
    if _settings_instance is None or reload:
        _settings_instance = Settings()
    return _settings_instance
