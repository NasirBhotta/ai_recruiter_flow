"""
Offline tests for interview email safety gates, duplicate-send prevention,
and durable state verification.
"""

from pathlib import Path
import pytest

from recruitflow.config import Settings
from recruitflow.models import (
    CandidateRecord,
    CandidateStatus,
    OutboxRecord,
)
from recruitflow import db
from recruitflow.workflow import WorkflowService


@pytest.fixture
def workflow_setup(tmp_path):
    """Create isolated test workflow service with in-memory/temp SQLite."""
    db_path = tmp_path / "test_recruitflow.db"
    sample_dir = tmp_path / "sample_cvs"
    sample_dir.mkdir()
    db.init_db(db_path)

    settings = Settings(
        DEMO_MODE=True,
        ENABLE_EMAIL_SEND=False,
        DATABASE_PATH=str(db_path),
        SAMPLE_CVS_DIR=str(sample_dir),
        SCHEDULING_URL="https://calendly.com/test-org/30min",
        DEMO_RECIPIENT_OVERRIDE=None,
    )
    service = WorkflowService(settings)
    return service, db_path


def test_send_requires_explicit_recruiter_approval(workflow_setup):
    """Test safety gate requiring explicit recruiter approval."""
    service, db_path = workflow_setup

    candidate = CandidateRecord(
        candidate_id="cand_test_1",
        received_at="2026-10-07T10:00:00Z",
        name="Alice Chen",
        email="alice.chen@example.com",
        normalized_email="alice.chen@example.com",
        skills=["Python"],
        status=CandidateStatus.INTERVIEW,
    )
    db.save_candidate(db_path, candidate)

    # Attempt send without explicit approval
    success, msg = service.send_interview_invitation("cand_test_1", explicit_approval=False)
    assert not success
    assert "Explicit recruiter approval is mandatory" in msg

    # State in DB must still be unsent
    reloaded = db.get_candidate(db_path, "cand_test_1")
    assert reloaded.interview_email_sent_at is None


def test_send_requires_interview_status(workflow_setup):
    """Test safety gate blocking send if candidate status is not 'Interview'."""
    service, db_path = workflow_setup

    for status in [CandidateStatus.PENDING_REVIEW, CandidateStatus.HOLD, CandidateStatus.REJECTED]:
        cid = f"cand_{status.name.lower()}"
        cand = CandidateRecord(
            candidate_id=cid,
            received_at="2026-10-07T10:00:00Z",
            name="Test Candidate",
            email="test@example.com",
            normalized_email="test@example.com",
            status=status,
        )
        db.save_candidate(db_path, cand)

        success, msg = service.send_interview_invitation(cid, explicit_approval=True)
        assert not success
        assert "Candidate status is" in msg


def test_duplicate_send_prevention(workflow_setup):
    """Test durable state prevents re-sending interview invitation once dispatched."""
    service, db_path = workflow_setup

    candidate = CandidateRecord(
        candidate_id="cand_alice",
        received_at="2026-10-07T10:00:00Z",
        name="Alice Chen",
        email="alice.chen@example.com",
        normalized_email="alice.chen@example.com",
        skills=["Python"],
        status=CandidateStatus.INTERVIEW,
    )
    db.save_candidate(db_path, candidate)

    # First send with explicit approval -> should succeed (simulated in demo mode)
    success1, msg1 = service.send_interview_invitation("cand_alice", explicit_approval=True)
    assert success1
    assert "SIMULATED OUTBOX" in msg1

    # Verify state in database
    reloaded = db.get_candidate(db_path, "cand_alice")
    assert reloaded.interview_email_sent_at is not None
    assert reloaded.interview_email_status == "simulated"

    # Second send attempt MUST fail and be blocked!
    success2, msg2 = service.send_interview_invitation("cand_alice", explicit_approval=True)
    assert not success2
    assert "already dispatched" in msg2

    # Check outbox has exactly 1 entry
    outbox = db.get_outbox_records(db_path)
    assert len(outbox) == 1


def test_uncertain_send_state_blocks_duplicate_send(workflow_setup):
    """Test that uncertain send state requires manual reconciliation before retry."""
    service, db_path = workflow_setup

    candidate = CandidateRecord(
        candidate_id="cand_bob",
        received_at="2026-10-07T10:00:00Z",
        name="Bob Miller",
        email="bob.miller@example.org",
        normalized_email="bob.miller@example.org",
        skills=["AWS"],
        status=CandidateStatus.INTERVIEW,
        interview_email_status="uncertain",
    )
    db.save_candidate(db_path, candidate)

    success, msg = service.send_interview_invitation("cand_bob", explicit_approval=True)
    assert not success
    assert "Previous dispatch outcome is uncertain" in msg


def test_demo_recipient_override_routing(tmp_path):
    """Test that DEMO_RECIPIENT_OVERRIDE reroutes email destination cleanly."""
    db_path = tmp_path / "test_recruitflow.db"
    sample_dir = tmp_path / "sample_cvs"
    sample_dir.mkdir()
    db.init_db(db_path)

    override_email = "recruiter-my-test-inbox@example.com"
    settings = Settings(
        DEMO_MODE=True,
        ENABLE_EMAIL_SEND=False,
        DATABASE_PATH=str(db_path),
        SAMPLE_CVS_DIR=str(sample_dir),
        DEMO_RECIPIENT_OVERRIDE=override_email,
    )
    service = WorkflowService(settings)

    candidate = CandidateRecord(
        candidate_id="cand_alice_override",
        received_at="2026-10-07T10:00:00Z",
        name="Alice Chen",
        email="alice.chen@example.com",
        normalized_email="alice.chen@example.com",
        skills=["Python"],
        status=CandidateStatus.INTERVIEW,
    )
    db.save_candidate(db_path, candidate)

    # Check preview
    preview = service.prepare_interview_email_preview("cand_alice_override")
    assert preview is not None
    assert preview.recipient == "alice.chen@example.com"
    assert preview.effective_recipient == override_email
    assert preview.is_override is True
    assert override_email in preview.body_text

    # Send invitation
    success, _ = service.send_interview_invitation("cand_alice_override", explicit_approval=True)
    assert success

    # Verify outbox record
    outbox = db.get_outbox_records(db_path)
    assert len(outbox) == 1
    assert outbox[0].recipient == override_email
    assert outbox[0].original_recipient == "alice.chen@example.com"
