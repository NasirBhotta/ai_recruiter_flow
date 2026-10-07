"""
Offline tests for attachment deduplication and candidate email reconciliation.
"""

import tempfile
from pathlib import Path
import pytest

from recruitflow.config import Settings
from recruitflow.models import (
    AttachmentInfo,
    CandidateRecord,
    CandidateStatus,
    ExtractionResult,
)
from recruitflow import db
from recruitflow.workflow import WorkflowService


@pytest.fixture
def temp_env(tmp_path):
    """Set up temporary database and sample directory for isolated tests."""
    db_path = tmp_path / "test_recruitflow.db"
    sample_dir = tmp_path / "sample_cvs"
    sample_dir.mkdir()
    db.init_db(db_path)

    settings = Settings(
        DEMO_MODE=True,
        DATABASE_PATH=str(db_path),
        SAMPLE_CVS_DIR=str(sample_dir),
    )
    return settings, db_path, sample_dir


def test_sqlite_attachment_deduplication_ledger(temp_env):
    """Test low-level SQLite deduplication ledger idempotency."""
    _, db_path, _ = temp_env

    msg_id = "msg_abc123"
    att_id = "att_xyz789"

    # Initially not processed
    assert not db.is_attachment_processed(db_path, msg_id, att_id)

    # Record attachment
    db.record_processed_attachment(
        db_path, msg_id, att_id, "resume.pdf", status="success"
    )

    # Should now report as processed
    assert db.is_attachment_processed(db_path, msg_id, att_id)

    # Re-recording same key does not fail (idempotent primary key)
    db.record_processed_attachment(
        db_path, msg_id, att_id, "resume.pdf", status="success"
    )
    assert db.is_attachment_processed(db_path, msg_id, att_id)


def test_workflow_skips_duplicate_attachments(temp_env):
    """Test that WorkflowService skips processing attachments already in ledger."""
    settings, db_path, _ = temp_env
    service = WorkflowService(settings)

    att = AttachmentInfo(
        message_id="msg_001",
        attachment_id="att_001",
        filename="alice_chen_backend.pdf",
        size_bytes=1000,
        data_bytes=b"%PDF-1.4 dummy valid data with sufficient text length to pass the minimal readable threshold check",
        received_at="2026-10-07T12:00:00Z",
    )

    stats = {"received": 1, "processed": 0, "skipped": 0, "errors": 0}

    # First run: should process
    service._process_single_attachment(att, stats)
    assert stats["processed"] == 1
    assert stats["skipped"] == 0

    # Second run with identical attachment: must be skipped
    stats2 = {"received": 1, "processed": 0, "skipped": 0, "errors": 0}
    service._process_single_attachment(att, stats2)
    assert stats2["processed"] == 0
    assert stats2["skipped"] == 1


def test_candidate_reconciliation_email_normalization(temp_env):
    """Test case-insensitive email normalization and deduplication."""
    _, db_path, _ = temp_env

    rec1 = CandidateRecord(
        candidate_id="cand_1",
        received_at="2026-10-07T10:00:00Z",
        name="Alice Chen",
        email="Alice.Chen@Example.COM",
        normalized_email="alice.chen@example.com",
        skills=["Python"],
        status=CandidateStatus.PENDING_REVIEW,
    )
    db.save_candidate(db_path, rec1)

    # Search with lower, upper, or mixed case should find same record
    found = db.find_candidate_by_email(db_path, "ALICE.CHEN@EXAMPLE.COM")
    assert found is not None
    assert found.candidate_id == "cand_1"
    assert found.name == "Alice Chen"


def test_candidate_reconciliation_ambiguous_name_conflict(temp_env):
    """
    Test that an application with an existing email but a conflicting candidate name
    is flagged as ambiguous and routed to Needs Review.
    """
    settings, db_path, _ = temp_env
    service = WorkflowService(settings)

    # Pre-populate candidate Alice Chen
    existing = CandidateRecord(
        candidate_id="cand_orig",
        received_at="2026-10-07T08:00:00Z",
        name="Alice Chen",
        email="alice.chen@example.com",
        normalized_email="alice.chen@example.com",
        skills=["Python"],
        status=CandidateStatus.PENDING_REVIEW,
    )
    db.save_candidate(db_path, existing)

    # Mock the extractor to return a different name with the SAME email address
    class MockConflictExtractor:
        def extract(self, text):
            return ExtractionResult(
                name="Dan Developer",
                email="alice.chen@example.com",
                skills=["Java"],
                experience_summary="3 years in Java",
                short_summary="Java developer.",
                missing_information=[],
            )

    service.extractor = MockConflictExtractor()

    sample_pdf = Path("data/sample_cvs/alice_chen_backend.pdf")
    pdf_bytes = sample_pdf.read_bytes() if sample_pdf.exists() else b"%PDF-1.4"

    att = AttachmentInfo(
        message_id="msg_dan",
        attachment_id="att_dan",
        filename="dan_resume.pdf",
        size_bytes=len(pdf_bytes),
        data_bytes=pdf_bytes,
    )
    stats = {"received": 1, "processed": 0, "skipped": 0, "errors": 0}
    service._process_single_attachment(att, stats)

    # Check candidate saved in DB
    all_cands = db.get_all_candidates(db_path)
    dan_record = next((c for c in all_cands if c.source_message_id == "msg_dan"), None)

    assert dan_record is not None
    assert dan_record.reconciliation_flag == "ambiguous"
    assert dan_record.status == CandidateStatus.NEEDS_REVIEW
