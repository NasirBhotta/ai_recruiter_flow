"""
Data models and schemas for RecruitFlow.
"""

from __future__ import annotations

from enum import Enum
import json
from typing import Any
from pydantic import BaseModel, Field, field_validator


class CandidateStatus(str, Enum):
    PENDING_REVIEW = "Pending Review"
    NEEDS_REVIEW = "Needs Review"
    INTERVIEW = "Interview"
    HOLD = "Hold"
    REJECTED = "Rejected"


class ExtractionResult(BaseModel):
    """
    Schema for Gemini structured extraction from resumes.
    Strictly factual; no qualification scores or hallucinated values.
    """
    name: str | None = Field(
        default=None,
        description="Full legal or professional name of the candidate, or null if missing.",
    )
    email: str | None = Field(
        default=None,
        description="Contact email address of the candidate, or null if missing.",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Technical, professional, and domain skills explicitly stated in the CV.",
    )
    experience_summary: str | None = Field(
        default=None,
        description="Factual summary of work history, years of experience, and previous roles stated in the CV.",
    )
    short_summary: str | None = Field(
        default=None,
        description="2-3 sentence factual overview of the candidate's professional background.",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Standard candidate fields not provided in the CV (e.g., phone, education, degree, portfolio, explicit years of experience).",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip().lower()
        return s if s and "@" in s else None


class AttachmentInfo(BaseModel):
    """Represents a discovered attachment from Gmail or local sample intake."""
    message_id: str
    attachment_id: str
    filename: str
    size_bytes: int
    data_bytes: bytes | None = None
    sender: str = ""
    subject: str = ""
    received_at: str = ""


class CandidateRecord(BaseModel):
    """
    Represents a candidate record stored in SQLite and synchronized to Google Sheets.
    """
    candidate_id: str
    received_at: str
    name: str | None = None
    email: str | None = None
    normalized_email: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience_summary: str | None = None
    short_summary: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    source_message_id: str = ""
    attachment_id: str = ""
    attachment_filename: str = ""
    status: CandidateStatus = CandidateStatus.PENDING_REVIEW
    processing_error: str | None = None
    interview_email_sent_at: str | None = None
    interview_email_status: str = "none"  # "none", "pending_approval", "sent", "simulated", "uncertain", "failed"
    reconciliation_flag: str = "normal"   # "normal", "ambiguous", "duplicate_updated"
    updated_at: str = ""

    def to_sheet_row(self) -> list[str]:
        """Convert to ordered list of columns for Google Sheet export."""
        return [
            self.candidate_id,
            self.received_at,
            self.name or "Unknown",
            self.email or "Unknown",
            ", ".join(self.skills) if self.skills else "None listed",
            self.experience_summary or "None listed",
            ", ".join(self.missing_information) if self.missing_information else "None noted",
            self.source_message_id,
            self.status.value,
            self.processing_error or "",
            self.interview_email_sent_at or "",
        ]

    @classmethod
    def sheet_headers(cls) -> list[str]:
        return [
            "candidate_id",
            "received_at",
            "name",
            "email",
            "skills",
            "experience_summary",
            "missing_information",
            "source_message_id",
            "status",
            "processing_error",
            "interview_email_sent_at",
        ]


class EmailPreview(BaseModel):
    """Prepared interview invitation preview for recruiter approval."""
    candidate_id: str
    candidate_name: str
    recipient: str
    effective_recipient: str
    subject: str
    body_text: str
    body_html: str
    scheduling_url: str
    is_override: bool
    mode: str  # "LIVE" or "SIMULATED"


class OutboxRecord(BaseModel):
    """Log record of an interview email sent or simulated."""
    id: int | None = None
    candidate_id: str
    recipient: str
    original_recipient: str
    subject: str
    body: str
    sent_at: str
    mode: str
    status: str
