"""
Offline tests for failure recovery, scanned PDF routing, and Sheets resilience.
"""

from pathlib import Path
import pytest

from recruitflow.config import Settings
from recruitflow.models import (
    AttachmentInfo,
    CandidateRecord,
    CandidateStatus,
)
from recruitflow import db
from recruitflow.workflow import WorkflowService
from recruitflow.sheets_service import SheetsError
from recruitflow.lock import WorkerLock


def test_scanned_unreadable_pdf_routes_to_needs_review(tmp_path):
    """Test that scanned/unreadable documents are safely routed to Needs Review."""
    db_path = tmp_path / "test_recruitflow.db"
    sample_dir = tmp_path / "sample_cvs"
    sample_dir.mkdir()
    db.init_db(db_path)

    settings = Settings(
        DEMO_MODE=True,
        DATABASE_PATH=str(db_path),
        SAMPLE_CVS_DIR=str(sample_dir),
    )
    service = WorkflowService(settings)

    # Use actual generated charlie_smith_scanned.pdf from data/sample_cvs
    scanned_sample = Path("data/sample_cvs/charlie_smith_scanned.pdf")
    if scanned_sample.exists():
        data_bytes = scanned_sample.read_bytes()
    else:
        # Fallback minimal dummy PDF without text
        data_bytes = b"%PDF-1.4 minimal dummy binary stream without text"

    att = AttachmentInfo(
        message_id="msg_scanned_001",
        attachment_id="att_scanned_001",
        filename="charlie_smith_scanned.pdf",
        size_bytes=len(data_bytes),
        data_bytes=data_bytes,
    )
    stats = {"received": 1, "processed": 0, "skipped": 0, "errors": 0}

    service._process_single_attachment(att, stats)

    # Inspect SQLite database
    candidates = db.get_all_candidates(db_path)
    assert len(candidates) == 1
    record = candidates[0]
    assert record.status == CandidateStatus.NEEDS_REVIEW
    assert record.reconciliation_flag == "unreadable_pdf"
    assert record.processing_error is not None
    assert "insufficient extractable text" in record.processing_error.lower() or "invalid" in record.processing_error.lower()


def test_partial_sheets_failure_retains_sqlite_state(tmp_path):
    """
    Test recovery behavior when Google Sheets sync fails:
    SQLite candidate record and deduplication must be preserved safely.
    """
    db_path = tmp_path / "test_recruitflow.db"
    sample_dir = tmp_path / "sample_cvs"
    sample_dir.mkdir()
    db.init_db(db_path)

    settings = Settings(
        DEMO_MODE=True,
        DATABASE_PATH=str(db_path),
        SAMPLE_CVS_DIR=str(sample_dir),
    )
    service = WorkflowService(settings)

    # Inject a failing mock Sheets client
    class FailingSheetsClient:
        def upsert_candidate(self, candidate):
            raise SheetsError("Simulated Google Sheets API quota exceeded / network outage.")

    service.sheets_client = FailingSheetsClient()

    sample_pdf = Path("data/sample_cvs/alice_chen_backend.pdf")
    pdf_bytes = sample_pdf.read_bytes() if sample_pdf.exists() else b"%PDF-1.4"

    att = AttachmentInfo(
        message_id="msg_resilience_001",
        attachment_id="att_resilience_001",
        filename="alice_chen_backend.pdf",
        size_bytes=len(pdf_bytes),
        data_bytes=pdf_bytes,
    )
    stats = {"received": 1, "processed": 0, "skipped": 0, "errors": 0}

    # Processing should NOT crash the pipeline
    service._process_single_attachment(att, stats)

    # Candidate MUST be saved in SQLite
    candidates = db.get_all_candidates(db_path)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.email == "alice.chen@example.com"
    # Deduplication MUST still be recorded in SQLite
    assert db.is_attachment_processed(db_path, "msg_resilience_001", "att_resilience_001")
    # Processing error notes the pending sheets sync
    assert "Sheets Sync Pending" in (cand.processing_error or "")


def test_worker_lock_prevents_overlap(tmp_path):
    """Test WorkerLock prevents concurrent process execution."""
    db_path = tmp_path / "test_recruitflow.db"
    db.init_db(db_path)

    # First lock acquired
    with WorkerLock(db_path, lock_name="test_lock") as lock1:
        assert lock1 is True

        # Second lock attempt must fail
        with WorkerLock(db_path, lock_name="test_lock") as lock2:
            assert lock2 is False
