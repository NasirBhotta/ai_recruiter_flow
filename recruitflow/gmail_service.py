"""
Gmail Intake and Dispatch Service for RecruitFlow.
Supports both Live Google Workspace/Gmail API and simulated Demo Mode intake.
"""

from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
import logging
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from recruitflow.models import AttachmentInfo, EmailPreview

logger = logging.getLogger(__name__)


def build_interview_email_content(
    candidate_name: str,
    scheduling_url: str,
    sender_name: str = "RecruitFlow Talent Team",
) -> tuple[str, str, str]:
    """
    Construct approved email subject, plain text body, and HTML body.
    Never fabricates meeting availability; relies exclusively on scheduling URL.
    """
    first_name = candidate_name.split()[0] if candidate_name else "Candidate"
    subject = f"Interview Invitation - {sender_name}"

    body_text = f"""Hi {first_name},

Thank you for your interest in joining our team! We reviewed your application and were impressed by your background and experience.

We would love to invite you to an introductory 30-minute interview with our engineering team.

Please select a time that works best for your schedule using our calendar link below:
{scheduling_url}

If you have any questions before our conversation, please reply directly to this email.

Best regards,
{sender_name}
"""

    body_html = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #2d3748; max-width: 600px; margin: 0 auto; padding: 20px;">
  <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 30px;">
    <h2 style="color: #1a202c; margin-top: 0;">Interview Invitation</h2>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>Thank you for your interest in joining our team! We reviewed your application and were impressed by your background and experience.</p>
    <p>We would love to invite you to an introductory 30-minute interview with our engineering team.</p>
    <div style="margin: 30px 0; text-align: center;">
      <a href="{scheduling_url}" style="background-color: #2b6cb0; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; display: inline-block;">Schedule Your Interview</a>
    </div>
    <p style="font-size: 14px; color: #718096;">Or copy this link to your browser: <br><a href="{scheduling_url}" style="color: #3182ce;">{scheduling_url}</a></p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 25px 0;">
    <p style="margin-bottom: 0; font-size: 14px; color: #4a5568;">Best regards,<br><strong>{sender_name}</strong></p>
  </div>
</body>
</html>
"""
    return subject, body_text, body_html


class GmailService:
    """Live Gmail API client for polling attachments and sending invitations."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build("gmail", "v1", credentials=self.credentials, cache_discovery=False)

    def fetch_pdf_attachments(self, query: str, max_results: int = 15) -> list[AttachmentInfo]:
        """
        Poll Gmail inbox matching query and extract metadata for PDF attachments.
        """
        attachments: list[AttachmentInfo] = []
        try:
            logger.info(f"Querying Gmail messages with: {query} (max: {max_results})")
            results = self.service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
            messages = results.get("messages", [])
            logger.info(f"Found {len(messages)} matching email messages in Gmail.")

            for msg_meta in messages:
                msg_id = msg_meta["id"]
                msg = (
                    self.service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )

                # Extract headers
                headers = msg.get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
                sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
                internal_date_ms = int(msg.get("internalDate", "0"))
                received_iso = datetime.fromtimestamp(
                    internal_date_ms / 1000, tz=timezone.utc
                ).isoformat() if internal_date_ms else datetime.now(timezone.utc).isoformat()

                payload = msg.get("payload", {})

                # Helper to collect all parts recursively
                def collect_parts(p):
                    subparts = []
                    if "parts" in p:
                        for sp in p["parts"]:
                            subparts.extend(collect_parts(sp))
                    else:
                        subparts.append(p)
                    return subparts

                all_parts = collect_parts(payload)

                # Inspect all MIME parts
                for part in all_parts:
                    filename = part.get("filename", "")
                    mime_type = part.get("mimeType", "")
                    body = part.get("body", {})
                    attachment_id = body.get("attachmentId")

                    # Check for PDF
                    if filename.lower().endswith(".pdf") or mime_type == "application/pdf":
                        if attachment_id:
                            att_data = (
                                self.service.users()
                                .messages()
                                .attachments()
                                .get(userId="me", messageId=msg_id, id=attachment_id)
                                .execute()
                            )
                            raw_base64 = att_data.get("data", "")
                            # Decodes URL-safe base64
                            file_bytes = base64.urlsafe_b64decode(raw_base64.encode("utf-8"))
                        elif "data" in body:
                            file_bytes = base64.urlsafe_b64decode(body["data"].encode("utf-8"))
                            attachment_id = f"inline_{msg_id}"
                        else:
                            continue

                        attachments.append(
                            AttachmentInfo(
                                message_id=msg_id,
                                attachment_id=attachment_id or f"att_{msg_id}",
                                filename=filename or "resume.pdf",
                                size_bytes=len(file_bytes),
                                data_bytes=file_bytes,
                                sender=sender,
                                subject=subject,
                                received_at=received_iso,
                            )
                        )

        except Exception as e:
            logger.error(f"Error fetching Gmail attachments: {e}")
            raise

        return attachments

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> dict[str, Any]:
        """
        Send email via official Gmail API users().messages().send.
        """
        message = MIMEMultipart("alternative")
        message["to"] = to_email
        message["subject"] = subject

        part1 = MIMEText(body_text, "plain", "utf-8")
        message.attach(part1)

        if body_html:
            part2 = MIMEText(body_html, "html", "utf-8")
            message.attach(part2)

        raw_bytes = message.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

        sent_msg = (
            self.service.users()
            .messages()
            .send(userId="me", body={"raw": raw_b64})
            .execute()
        )
        logger.info(f"Dispatched live email via Gmail to {to_email}. Gmail Message ID: {sent_msg.get('id')}")
        return sent_msg


class DemoGmailService:
    """
    Simulated Gmail service for DEMO_MODE.
    Reads synthetic PDFs from sample directory and simulates dispatch.
    """

    def __init__(self, sample_dir: Path):
        self.sample_dir = sample_dir

    def fetch_pdf_attachments(self, query: str = "", max_results: int = 15) -> list[AttachmentInfo]:
        """Load synthetic resumes from local directory as simulated Gmail intake."""
        attachments: list[AttachmentInfo] = []
        if not self.sample_dir.exists():
            logger.warning(f"Sample CV directory does not exist: {self.sample_dir}")
            return attachments

        pdf_files = sorted(list(self.sample_dir.glob("*.pdf")))
        logger.info(f"[SIMULATED GMAIL] Scanning {len(pdf_files)} synthetic CV files in {self.sample_dir}")

        for idx, pdf_path in enumerate(pdf_files, start=1):
            file_bytes = pdf_path.read_bytes()
            stem = pdf_path.stem
            # Consistent deterministic synthetic IDs
            msg_id = f"demo_msg_{idx:03d}_{stem}"
            att_id = f"demo_att_{idx:03d}_{stem}"
            now_iso = datetime.now(timezone.utc).isoformat()

            attachments.append(
                AttachmentInfo(
                    message_id=msg_id,
                    attachment_id=att_id,
                    filename=pdf_path.name,
                    size_bytes=len(file_bytes),
                    data_bytes=file_bytes,
                    sender=f"{stem}@example.com",
                    subject=f"Application: Senior Role - {pdf_path.name}",
                    received_at=now_iso,
                )
            )

        return attachments
