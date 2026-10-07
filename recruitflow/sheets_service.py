"""
Google Sheets Candidate Tracker Integration for RecruitFlow.
Supports Live Google Sheets API sync and local Demo Mode spreadsheet emulation.
"""

from __future__ import annotations

import logging
from typing import Any
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from recruitflow.models import CandidateRecord

logger = logging.getLogger(__name__)


class SheetsError(Exception):
    """Raised when Google Sheets synchronization fails."""
    pass


class GoogleSheetsService:
    """Official Google Sheets API v4 client for tracking candidates."""

    def __init__(self, credentials: Credentials, spreadsheet_id: str, sheet_name: str = "Candidates"):
        self.credentials = credentials
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.service = build("sheets", "v4", credentials=self.credentials, cache_discovery=False)
        self._ensure_header()

    def _ensure_header(self) -> None:
        """Verify headers exist in row 1; write default headers if blank."""
        try:
            range_header = f"{self.sheet_name}!A1:K1"
            res = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=range_header)
                .execute()
            )
            rows = res.get("values", [])
            if not rows or not rows[0]:
                headers = CandidateRecord.sheet_headers()
                logger.info(f"Writing default candidate headers to {range_header}...")
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_header,
                    valueInputOption="RAW",
                    body={"values": [headers]},
                ).execute()
        except Exception as e:
            logger.error(f"Failed to verify or write Google Sheet headers: {e}")
            raise SheetsError(f"Google Sheet initialization error: {e}") from e

    def upsert_candidate(self, candidate: CandidateRecord) -> None:
        """
        Append candidate row or update existing row if candidate_id already exists.
        """
        try:
            # 1. Fetch existing candidate_ids in Column A
            col_a_range = f"{self.sheet_name}!A:A"
            res = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=col_a_range)
                .execute()
            )
            values = res.get("values", [])

            row_index: int | None = None
            for idx, row in enumerate(values, start=1):
                if row and row[0] == candidate.candidate_id:
                    row_index = idx
                    break

            row_data = candidate.to_sheet_row()

            if row_index is not None:
                # Update existing row
                update_range = f"{self.sheet_name}!A{row_index}:K{row_index}"
                logger.info(f"Updating existing row {row_index} for candidate {candidate.candidate_id}")
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=update_range,
                    valueInputOption="RAW",
                    body={"values": [row_data]},
                ).execute()
            else:
                # Append new row
                append_range = f"{self.sheet_name}!A1"
                logger.info(f"Appending new candidate {candidate.candidate_id} to sheet")
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range=append_range,
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [row_data]},
                ).execute()

        except Exception as e:
            logger.error(f"Failed to upsert candidate {candidate.candidate_id} in Google Sheets: {e}")
            raise SheetsError(f"Failed to sync with Google Sheet: {e}") from e


class DemoSheetsService:
    """
    In-memory / simulated Google Sheets service for DEMO_MODE.
    Mimics remote Google Sheet operations with clear logging and inspection.
    """

    def __init__(self):
        self.rows: dict[str, list[str]] = {}
        self.headers = CandidateRecord.sheet_headers()

    def upsert_candidate(self, candidate: CandidateRecord) -> None:
        """Record candidate into simulated spreadsheet."""
        row_data = candidate.to_sheet_row()
        is_update = candidate.candidate_id in self.rows
        self.rows[candidate.candidate_id] = row_data
        action = "Updated existing row in" if is_update else "Appended new row to"
        logger.info(f"[SIMULATED GOOGLE SHEET] {action} sheet for candidate: {candidate.name} ({candidate.candidate_id})")

    def get_all_rows(self) -> list[list[str]]:
        """Return headers plus all simulated rows."""
        return [self.headers] + list(self.rows.values())
