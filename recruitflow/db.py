"""
Durable SQLite persistence and processing ledger for RecruitFlow.
Guarantees deduplication, idempotent intake, and auditability.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any
from datetime import datetime, timezone

from recruitflow.models import (
    CandidateRecord,
    CandidateStatus,
    OutboxRecord,
)


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Create an SQLite connection with WAL enabled and row factory."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    """Initialize database tables and indices."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Deduplication ledger for Gmail / sample attachments
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_attachments (
                message_id TEXT NOT NULL,
                attachment_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                PRIMARY KEY (message_id, attachment_id)
            )
            """
        )

        # 2. Candidate records
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                received_at TEXT NOT NULL,
                name TEXT,
                email TEXT,
                normalized_email TEXT,
                skills_json TEXT NOT NULL,
                experience_summary TEXT,
                short_summary TEXT,
                missing_info_json TEXT NOT NULL,
                source_message_id TEXT NOT NULL,
                attachment_id TEXT NOT NULL,
                attachment_filename TEXT NOT NULL,
                status TEXT NOT NULL,
                processing_error TEXT,
                interview_email_sent_at TEXT,
                interview_email_status TEXT NOT NULL,
                reconciliation_flag TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates (normalized_email)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates (status)"
        )

        # 3. Outbox table for audit logging
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                recipient TEXT NOT NULL,
                original_recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )

        # 4. Worker lock table to prevent overlapping executions
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_locks (
                lock_name TEXT PRIMARY KEY,
                acquired_at TEXT NOT NULL,
                owner_info TEXT NOT NULL
            )
            """
        )

        conn.commit()


def is_attachment_processed(
    db_path: str | Path, message_id: str, attachment_id: str
) -> bool:
    """Check if a specific attachment has already been processed."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM processed_attachments
            WHERE message_id = ? AND attachment_id = ?
            """,
            (message_id, attachment_id),
        ).fetchone()
        return row is not None


def record_processed_attachment(
    db_path: str | Path,
    message_id: str,
    attachment_id: str,
    filename: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Record an attachment in the deduplication ledger."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO processed_attachments
            (message_id, attachment_id, filename, processed_at, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, attachment_id, filename, now_iso, status, error_message),
        )
        conn.commit()


def row_to_candidate(row: sqlite3.Row) -> CandidateRecord:
    """Convert an SQLite Row to a CandidateRecord."""
    skills = json.loads(row["skills_json"]) if row["skills_json"] else []
    missing_info = (
        json.loads(row["missing_info_json"]) if row["missing_info_json"] else []
    )
    return CandidateRecord(
        candidate_id=row["candidate_id"],
        received_at=row["received_at"],
        name=row["name"],
        email=row["email"],
        normalized_email=row["normalized_email"],
        skills=skills,
        experience_summary=row["experience_summary"],
        short_summary=row["short_summary"],
        missing_information=missing_info,
        source_message_id=row["source_message_id"],
        attachment_id=row["attachment_id"],
        attachment_filename=row["attachment_filename"],
        status=CandidateStatus(row["status"]),
        processing_error=row["processing_error"],
        interview_email_sent_at=row["interview_email_sent_at"],
        interview_email_status=row["interview_email_status"],
        reconciliation_flag=row["reconciliation_flag"],
        updated_at=row["updated_at"],
    )


def find_candidate_by_email(
    db_path: str | Path, email: str | None
) -> CandidateRecord | None:
    """Search for existing candidate by normalized email."""
    if not email:
        return None
    normalized = email.strip().lower()
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM candidates WHERE normalized_email = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if row:
            return row_to_candidate(row)
        return None


def get_candidate(
    db_path: str | Path, candidate_id: str
) -> CandidateRecord | None:
    """Retrieve single candidate by ID."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row:
            return row_to_candidate(row)
        return None


def get_all_candidates(
    db_path: str | Path, status: CandidateStatus | None = None
) -> list[CandidateRecord]:
    """Retrieve all candidates, optionally filtered by status."""
    with get_connection(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM candidates WHERE status = ? ORDER BY received_at DESC",
                (status.value,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM candidates ORDER BY received_at DESC"
            ).fetchall()
        return [row_to_candidate(r) for r in rows]


def save_candidate(db_path: str | Path, record: CandidateRecord) -> None:
    """Insert or update candidate record in SQLite."""
    now_iso = datetime.now(timezone.utc).isoformat()
    record.updated_at = now_iso
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO candidates (
                candidate_id, received_at, name, email, normalized_email,
                skills_json, experience_summary, short_summary, missing_info_json,
                source_message_id, attachment_id, attachment_filename,
                status, processing_error, interview_email_sent_at,
                interview_email_status, reconciliation_flag, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.candidate_id,
                record.received_at,
                record.name,
                record.email,
                record.normalized_email,
                json.dumps(record.skills),
                record.experience_summary,
                record.short_summary,
                json.dumps(record.missing_information),
                record.source_message_id,
                record.attachment_id,
                record.attachment_filename,
                record.status.value,
                record.processing_error,
                record.interview_email_sent_at,
                record.interview_email_status,
                record.reconciliation_flag,
                record.updated_at,
            ),
        )
        conn.commit()


def update_candidate_status(
    db_path: str | Path, candidate_id: str, new_status: CandidateStatus
) -> bool:
    """Manually update candidate review status."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE candidates
            SET status = ?, updated_at = ?
            WHERE candidate_id = ?
            """,
            (new_status.value, now_iso, candidate_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def update_interview_send_state(
    db_path: str | Path,
    candidate_id: str,
    sent_at: str | None,
    send_status: str,
    error_note: str | None = None,
) -> bool:
    """Persist interview send outcome idempotently."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE candidates
            SET interview_email_sent_at = ?,
                interview_email_status = ?,
                processing_error = COALESCE(?, processing_error),
                updated_at = ?
            WHERE candidate_id = ?
            """,
            (sent_at, send_status, error_note, now_iso, candidate_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def record_outbox_message(db_path: str | Path, record: OutboxRecord) -> int:
    """Append sent or simulated email message to outbox log."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO outbox
            (candidate_id, recipient, original_recipient, subject, body, sent_at, mode, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.candidate_id,
                record.recipient,
                record.original_recipient,
                record.subject,
                record.body,
                record.sent_at,
                record.mode,
                record.status,
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0


def get_outbox_records(db_path: str | Path) -> list[OutboxRecord]:
    """Retrieve all logged outbox messages."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM outbox ORDER BY id DESC"
        ).fetchall()
        return [
            OutboxRecord(
                id=r["id"],
                candidate_id=r["candidate_id"],
                recipient=r["recipient"],
                original_recipient=r["original_recipient"],
                subject=r["subject"],
                body=r["body"],
                sent_at=r["sent_at"],
                mode=r["mode"],
                status=r["status"],
            )
            for r in rows
        ]


def get_dashboard_counts(db_path: str | Path) -> dict[str, int]:
    """Calculate key performance indicators for dashboard."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        total_attachments = cursor.execute(
            "SELECT COUNT(*) FROM processed_attachments"
        ).fetchone()[0]
        total_candidates = cursor.execute(
            "SELECT COUNT(*) FROM candidates"
        ).fetchone()[0]
        pending_review = cursor.execute(
            "SELECT COUNT(*) FROM candidates WHERE status = ?",
            (CandidateStatus.PENDING_REVIEW.value,),
        ).fetchone()[0]
        needs_review = cursor.execute(
            "SELECT COUNT(*) FROM candidates WHERE status = ?",
            (CandidateStatus.NEEDS_REVIEW.value,),
        ).fetchone()[0]
        interview_status = cursor.execute(
            "SELECT COUNT(*) FROM candidates WHERE status = ?",
            (CandidateStatus.INTERVIEW.value,),
        ).fetchone()[0]
        sent_emails = cursor.execute(
            "SELECT COUNT(*) FROM candidates WHERE interview_email_sent_at IS NOT NULL"
        ).fetchone()[0]

        return {
            "total_attachments": total_attachments,
            "total_candidates": total_candidates,
            "pending_review": pending_review,
            "needs_review": needs_review,
            "interview_ready": interview_status,
            "invitations_sent": sent_emails,
        }


def reset_database(db_path: str | Path) -> None:
    """Clear tables for demonstration resets."""
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM processed_attachments")
        conn.execute("DELETE FROM candidates")
        conn.execute("DELETE FROM outbox")
        conn.execute("DELETE FROM worker_locks")
        conn.commit()
