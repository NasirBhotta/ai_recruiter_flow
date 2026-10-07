"""
RecruitFlow Core Workflow Orchestrator.
Manages intake, deduplication, Gemini extraction, reconciliation, Sheets sync,
and safe, recruiter-approved interview email dispatch.
"""

from __future__ import annotations

import logging
from pathlib import Path
import uuid
from datetime import datetime, timezone
from typing import Any

from recruitflow.config import Settings, get_settings
from recruitflow.models import (
    CandidateRecord,
    CandidateStatus,
    ExtractionResult,
    AttachmentInfo,
    EmailPreview,
    OutboxRecord,
)
from recruitflow import db
from recruitflow.lock import WorkerLock
from recruitflow.auth import get_google_credentials
from recruitflow.pdf_parser import extract_text_from_pdf
from recruitflow.extractor import GeminiExtractor, ExtractionError
from recruitflow.gmail_service import (
    GmailService,
    DemoGmailService,
    build_interview_email_content,
)
from recruitflow.sheets_service import GoogleSheetsService, DemoSheetsService, SheetsError

logger = logging.getLogger(__name__)


class WorkflowService:
    """End-to-end recruitment automation pipeline service."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.db_path = self.settings.db_path_resolved
        # Ensure database is initialized
        db.init_db(self.db_path)

        # Initialize Extractor
        self.extractor = GeminiExtractor(
            api_key=self.settings.gemini_api_key,
            model_name=self.settings.gemini_model,
            demo_mode=self.settings.demo_mode,
        )

        # Service clients (lazy-loaded or initialized based on mode)
        self.gmail_client: GmailService | DemoGmailService | None = None
        self.sheets_client: GoogleSheetsService | DemoSheetsService | None = None
        self._init_integrations()

    def _init_integrations(self) -> None:
        """Initialize live Google services or demo services based on mode."""
        if self.settings.demo_mode:
            logger.info("Initializing in DEMO MODE: Using simulated Gmail and Sheets services.")
            self.gmail_client = DemoGmailService(sample_dir=self.settings.sample_cvs_dir_resolved)
            self.sheets_client = DemoSheetsService()
            return

        # LIVE MODE
        try:
            creds = get_google_credentials(
                client_secrets_path=self.settings.client_secrets_resolved,
                token_path=self.settings.token_file_resolved,
                interactive=False,
            )
            if creds:
                self.gmail_client = GmailService(credentials=creds)
                if self.settings.spreadsheet_id:
                    self.sheets_client = GoogleSheetsService(
                        credentials=creds,
                        spreadsheet_id=self.settings.spreadsheet_id,
                        sheet_name=self.settings.sheet_name,
                    )
                else:
                    logger.warning("No SPREADSHEET_ID configured in live mode. Using demo sheets client.")
                    self.sheets_client = DemoSheetsService()
        except Exception as e:
            logger.warning(
                f"Could not initialize live Google integrations: {e}. "
                "Falling back to demo simulation services."
            )
            self.gmail_client = DemoGmailService(sample_dir=self.settings.sample_cvs_dir_resolved)
            self.sheets_client = DemoSheetsService()

    def reconnect_services(self) -> bool:
        """Reload credentials and reconnect live Gmail and Google Sheets services."""
        self._init_integrations()
        return isinstance(self.gmail_client, GmailService)

    def process_inbox(self, query: str | None = None, force_demo: bool = False) -> dict[str, int]:
        """
        Poll inbox, deduplicate attachments, extract CV data, reconcile candidate,
        and update Sheets tracker.
        Protected by WorkerLock to prevent overlapping runs.
        """
        with WorkerLock(self.db_path) as acquired:
            if not acquired:
                logger.warning("Intake worker could not acquire lock. Another run is active. Skipping.")
                return {"received": 0, "processed": 0, "skipped": 0, "errors": 0}

            search_query = query if query is not None else self.settings.gmail_query
            client = (
                DemoGmailService(sample_dir=self.settings.sample_cvs_dir_resolved)
                if force_demo
                else self.gmail_client
            )
            mode_label = "Demo Samples" if force_demo or isinstance(client, DemoGmailService) else "Real Gmail"
            logger.info(f"Starting candidate intake processing run ({mode_label}, Query: '{search_query}')...")
            stats = {"received": 0, "processed": 0, "skipped": 0, "errors": 0}

            try:
                # 1. Fetch attachments
                attachments: list[AttachmentInfo] = client.fetch_pdf_attachments(
                    query=search_query
                )
                stats["received"] = len(attachments)
                logger.info(f"Retrieved {len(attachments)} total attachments from intake.")

                # 2. Process each attachment
                for att in attachments:
                    try:
                        self._process_single_attachment(att, stats)
                    except Exception as e:
                        logger.error(f"Error processing attachment {att.filename}: {e}", exc_info=True)
                        stats["errors"] += 1

            except Exception as e:
                logger.error(f"Intake pipeline encounter fatal error: {e}", exc_info=True)
                stats["errors"] += 1

            logger.info(f"Intake processing complete. Stats: {stats}")
            return stats

    def _process_single_attachment(self, att: AttachmentInfo, stats: dict[str, int]) -> None:
        """Process a single candidate attachment with idempotency checks."""
        # Check deduplication
        if db.is_attachment_processed(self.db_path, att.message_id, att.attachment_id):
            logger.info(
                f"Attachment already processed: {att.message_id}:{att.attachment_id} ({att.filename}). Skipping."
            )
            stats["skipped"] += 1
            return

        logger.info(f"Processing new attachment: {att.filename} ({att.size_bytes} bytes)")
        if not att.data_bytes:
            db.record_processed_attachment(
                self.db_path, att.message_id, att.attachment_id, att.filename,
                status="failed", error_message="Attachment payload data was empty."
            )
            stats["errors"] += 1
            return

        # 1. Local PDF Extraction & Scanned Detection
        parse_result = extract_text_from_pdf(
            att.data_bytes, max_size_mb=self.settings.max_attachment_size_mb
        )

        candidate_id = f"cand_{uuid.uuid4().hex[:8]}"
        received_at = att.received_at or datetime.now(timezone.utc).isoformat()

        if not parse_result.success:
            # Route to Needs Review immediately (scanned, unreadable, corrupted, oversized)
            logger.warning(f"PDF extraction unsuccessful for {att.filename}: {parse_result.error}")
            record = CandidateRecord(
                candidate_id=candidate_id,
                received_at=received_at,
                name=Path(att.filename).stem.replace("_", " ").title(),
                email=None,
                normalized_email=None,
                skills=[],
                experience_summary=None,
                short_summary="Unable to extract text automatically.",
                missing_information=["readable resume text"],
                source_message_id=att.message_id,
                attachment_id=att.attachment_id,
                attachment_filename=att.filename,
                status=CandidateStatus.NEEDS_REVIEW,
                processing_error=parse_result.error,
                reconciliation_flag="unreadable_pdf",
            )
            self._persist_and_sync_candidate(record, att, "needs_review", parse_result.error)
            stats["processed"] += 1
            return

        # 2. Structured Extraction via Gemini (Treating CV as untrusted data)
        try:
            extraction: ExtractionResult = self.extractor.extract(parse_result.text)
        except Exception as e:
            logger.error(f"Gemini structured extraction failed for {att.filename}: {e}")
            record = CandidateRecord(
                candidate_id=candidate_id,
                received_at=received_at,
                name=None,
                email=None,
                normalized_email=None,
                skills=[],
                experience_summary=None,
                short_summary="Extraction failed during LLM analysis.",
                missing_information=["all fields"],
                source_message_id=att.message_id,
                attachment_id=att.attachment_id,
                attachment_filename=att.filename,
                status=CandidateStatus.NEEDS_REVIEW,
                processing_error=f"LLM Extraction failed: {e}",
                reconciliation_flag="extraction_failure",
            )
            self._persist_and_sync_candidate(record, att, "needs_review", str(e))
            stats["processed"] += 1
            return

        # 3. Candidate Record Reconciliation
        normalized_email = extraction.email.lower() if extraction.email else None
        reconciliation_flag = "normal"
        initial_status = CandidateStatus.PENDING_REVIEW

        if normalized_email:
            existing = db.find_candidate_by_email(self.db_path, normalized_email)
            if existing:
                # Existing candidate re-application check
                if existing.name and extraction.name and existing.name.lower() != extraction.name.lower():
                    # Same email, different name -> Ambiguous identity conflict!
                    logger.warning(
                        f"Email conflict: '{normalized_email}' matched existing '{existing.name}' "
                        f"but new CV claims '{extraction.name}'. Flagging for review."
                    )
                    reconciliation_flag = "ambiguous"
                    initial_status = CandidateStatus.NEEDS_REVIEW
                else:
                    # Update to existing candidate profile
                    logger.info(f"Re-application detected for existing candidate {existing.candidate_id} ({normalized_email}).")
                    candidate_id = existing.candidate_id
                    reconciliation_flag = "updated_profile"

        # Construct CandidateRecord
        record = CandidateRecord(
            candidate_id=candidate_id,
            received_at=received_at,
            name=extraction.name,
            email=extraction.email,
            normalized_email=normalized_email,
            skills=extraction.skills,
            experience_summary=extraction.experience_summary,
            short_summary=extraction.short_summary,
            missing_information=extraction.missing_information,
            source_message_id=att.message_id,
            attachment_id=att.attachment_id,
            attachment_filename=att.filename,
            status=initial_status,
            processing_error=None,
            reconciliation_flag=reconciliation_flag,
        )

        self._persist_and_sync_candidate(record, att, "success", None)
        stats["processed"] += 1

    def _persist_and_sync_candidate(
        self,
        record: CandidateRecord,
        att: AttachmentInfo,
        att_status: str,
        att_error: str | None,
    ) -> None:
        """
        Durable SQLite record first, then sync to Google Sheet.
        If Sheet sync encounters an error, SQLite data remains safe and error is recorded.
        """
        # Save to SQLite durable ledger
        db.save_candidate(self.db_path, record)
        db.record_processed_attachment(
            self.db_path,
            att.message_id,
            att.attachment_id,
            att.filename,
            status=att_status,
            error_message=att_error,
        )

        # Sync to Google Sheets
        if self.sheets_client:
            try:
                self.sheets_client.upsert_candidate(record)
            except Exception as e:
                logger.error(
                    f"Google Sheets sync failed for candidate {record.candidate_id}: {e}. "
                    "SQLite persistence succeeded."
                )
                # Keep error recorded on candidate for recruiter visibility
                record.processing_error = f"Sheets Sync Pending: {e}"
                db.save_candidate(self.db_path, record)

    def set_candidate_status(
        self, candidate_id: str, new_status: CandidateStatus
    ) -> bool:
        """
        Recruiter manual status update (Interview, Hold, Rejected, etc.).
        Updates SQLite and syncs the updated status to Google Sheets.
        """
        success = db.update_candidate_status(self.db_path, candidate_id, new_status)
        if success and self.sheets_client:
            candidate = db.get_candidate(self.db_path, candidate_id)
            if candidate:
                try:
                    self.sheets_client.upsert_candidate(candidate)
                except Exception as e:
                    logger.warning(f"Could not sync status change to Google Sheet: {e}")
        return success

    def prepare_interview_email_preview(self, candidate_id: str) -> EmailPreview | None:
        """Generate email preview for recruiter review before dispatch."""
        candidate = db.get_candidate(self.db_path, candidate_id)
        if not candidate or not candidate.email:
            return None

        subject, body_text, body_html = build_interview_email_content(
            candidate_name=candidate.name or "Candidate",
            scheduling_url=self.settings.scheduling_url,
            sender_name=self.settings.sender_name,
        )

        override = self.settings.demo_recipient_override
        is_override = bool(override and override.strip())
        effective_recipient = override.strip() if is_override else candidate.email

        if is_override:
            banner = f"\n[NOTICE: Sent to override address '{effective_recipient}'. Original applicant was: {candidate.email}]\n\n"
            body_text = banner + body_text
            html_banner = f"<div style='background:#fef3c7;border:1px solid #f59e0b;padding:10px;margin-bottom:15px;border-radius:4px;'><strong>Test Mode:</strong> Sent to override address <code>{effective_recipient}</code>. Original applicant: {candidate.email}</div>"
            body_html = body_html.replace("<body style=\"", f"<body style=\"\"><div style=\"max-width:600px;margin:0 auto;\">{html_banner}</div>")

        mode = "SIMULATED" if (self.settings.demo_mode or not self.settings.enable_email_send) else "LIVE"

        return EmailPreview(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.name or "Candidate",
            recipient=candidate.email,
            effective_recipient=effective_recipient,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            scheduling_url=self.settings.scheduling_url,
            is_override=is_override,
            mode=mode,
        )

    def send_interview_invitation(
        self, candidate_id: str, explicit_approval: bool = False
    ) -> tuple[bool, str]:
        """
        Send interview invitation email with rigorous safety checks:
        1. Explicit recruiter approval required.
        2. Candidate status must be 'Interview'.
        3. Reject duplicate sends (durable send state).
        4. Reconcile uncertain send state.
        5. Live send disabled unless ENABLE_EMAIL_SEND=true.
        """
        # Safety Gate 1: Explicit Human Approval
        if not explicit_approval:
            return False, "Safety rejection: Explicit recruiter approval is mandatory to send interview emails."

        candidate = db.get_candidate(self.db_path, candidate_id)
        if not candidate:
            return False, f"Candidate {candidate_id} not found."

        # Safety Gate 2: Candidate Status must be Interview
        if candidate.status != CandidateStatus.INTERVIEW:
            return False, f"Safety rejection: Candidate status is '{candidate.status.value}', not 'Interview'."

        # Safety Gate 3: Duplicate Send Prevention
        if candidate.interview_email_sent_at is not None or candidate.interview_email_status in ["sent", "simulated"]:
            return False, f"Safety rejection: Interview invitation was already dispatched at {candidate.interview_email_sent_at}."

        if candidate.interview_email_status == "uncertain":
            return False, "Safety rejection: Previous dispatch outcome is uncertain. Human reconciliation required before retrying."

        if not candidate.email:
            return False, "Cannot send email: Candidate has no email address."

        # Prepare message content
        preview = self.prepare_interview_email_preview(candidate_id)
        if not preview:
            return False, "Could not construct email preview."

        now_iso = datetime.now(timezone.utc).isoformat()

        # Check Live vs Demo / Disabled
        is_live = (not self.settings.demo_mode) and self.settings.enable_email_send

        if not is_live:
            # Simulated send (Demo Mode or live sending disabled)
            logger.info(f"[SIMULATED SEND] Interview invitation logged for {candidate.name} ({preview.effective_recipient})")
            db.update_interview_send_state(
                self.db_path,
                candidate_id=candidate.candidate_id,
                sent_at=now_iso,
                send_status="simulated",
            )
            outbox_entry = OutboxRecord(
                candidate_id=candidate.candidate_id,
                recipient=preview.effective_recipient,
                original_recipient=candidate.email,
                subject=preview.subject,
                body=preview.body_text,
                sent_at=now_iso,
                mode="SIMULATED",
                status="SENT",
            )
            db.record_outbox_message(self.db_path, outbox_entry)

            # Sync update to Google Sheets
            candidate.interview_email_sent_at = now_iso
            candidate.interview_email_status = "simulated"
            if self.sheets_client:
                try:
                    self.sheets_client.upsert_candidate(candidate)
                except Exception as e:
                    logger.warning(f"Sheets update failed: {e}")

            msg = f"[SIMULATED OUTBOX] Interview invitation recorded for {preview.effective_recipient}. (ENABLE_EMAIL_SEND is false or DEMO_MODE is active)."
            return True, msg

        # LIVE GMAIL DISPATCH
        try:
            logger.info(f"Dispatching live email to {preview.effective_recipient} via Gmail API...")
            if not isinstance(self.gmail_client, GmailService):
                raise RuntimeError("Gmail client is not in live mode.")

            self.gmail_client.send_email(
                to_email=preview.effective_recipient,
                subject=preview.subject,
                body_text=preview.body_text,
                body_html=preview.body_html,
            )

            # Mark sent in SQLite durable ledger
            db.update_interview_send_state(
                self.db_path,
                candidate_id=candidate.candidate_id,
                sent_at=now_iso,
                send_status="sent",
            )
            outbox_entry = OutboxRecord(
                candidate_id=candidate.candidate_id,
                recipient=preview.effective_recipient,
                original_recipient=candidate.email,
                subject=preview.subject,
                body=preview.body_text,
                sent_at=now_iso,
                mode="LIVE",
                status="SENT",
            )
            db.record_outbox_message(self.db_path, outbox_entry)

            # Sync update to Google Sheets
            candidate.interview_email_sent_at = now_iso
            candidate.interview_email_status = "sent"
            if self.sheets_client:
                try:
                    self.sheets_client.upsert_candidate(candidate)
                except Exception as e:
                    logger.warning(f"Sheets update failed after email send: {e}")

            return True, f"Successfully dispatched live interview email to {preview.effective_recipient}."

        except Exception as e:
            logger.error(f"Live email dispatch error: {e}")
            # Mark as UNCERTAIN to avoid duplicate retries without human check
            db.update_interview_send_state(
                self.db_path,
                candidate_id=candidate.candidate_id,
                sent_at=None,
                send_status="uncertain",
                error_note=f"Send error (flagged uncertain): {e}",
            )
            return False, f"Email dispatch failed or uncertain: {e}. Flagged for human reconciliation."
