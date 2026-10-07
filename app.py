"""
RecruitFlow: Streamlined, Easy-to-Understand Recruiter Dashboard.
Designed for simple 3-step recruiting:
1. Scan Gmail for CVs (AI extracts name, skills, summary)
2. Review & 1-Click Decision (Interview, Hold, Reject)
3. 1-Click Approved Interview Email Dispatch & Google Sheets Sync
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import os
from pathlib import Path
import json
import pandas as pd
import streamlit as st

from recruitflow.config import get_settings
from recruitflow.models import CandidateStatus, CandidateRecord
from recruitflow.workflow import WorkflowService
from recruitflow import db
from recruitflow.auth import get_google_credentials, check_auth_status
from generate_samples import generate_all_samples

# Setup Page Configuration
st.set_page_config(
    page_title="RecruitFlow | AI Recruiter Hub",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for modern, clean, card-based recruiter interface
st.markdown(
    """
    <style>
    .candidate-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 18px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
    }
    .skill-tag {
        background-color: #eff6ff;
        color: #1d4ed8;
        border: 1px solid #bfdbfe;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 500;
        margin-right: 5px;
        margin-bottom: 5px;
        display: inline-block;
    }
    .missing-tag {
        background-color: #fef2f2;
        color: #b91c1c;
        border: 1px solid #fecaca;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 500;
        margin-right: 5px;
        display: inline-block;
    }
    .status-badge-interview {
        background-color: #dcfce7;
        color: #15803d;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.85rem;
    }
    .status-badge-review {
        background-color: #fef3c7;
        color: #b45309;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.85rem;
    }
    .status-badge-needs {
        background-color: #fee2e2;
        color: #b91c1c;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.85rem;
    }
    .email-box {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 16px;
        font-family: inherit;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

settings = get_settings()
service = WorkflowService(settings)
db_path = settings.db_path_resolved

# Check Google Credentials Status
auth_info = check_auth_status(
    settings.client_secrets_resolved, settings.token_file_resolved
)
is_google_connected = auth_info.get("is_valid", False)

# Check AI Provider
has_antigravity_ai = getattr(service.extractor, "_antigravity_llm", None) is not None

# --- SIDEBAR: GOOGLE SETUP & SYSTEM CONTROLS ---
with st.sidebar:
    st.title("🎯 RecruitFlow Hub")
    st.caption("AI-Powered Recruitment Automation")
    st.markdown("---")

    st.subheader("🔌 Google Connection")
    if is_google_connected:
        st.success("🟢 Real Gmail & Google Sheets Connected!")
    else:
        st.warning("🟡 Google Account Not Connected (Demo Mode Active)")
        with st.expander("🔑 Connect Real Google Account"):
            st.markdown(
                "Upload your `credentials.json` downloaded from Google Cloud Console:"
            )
            uploaded_cred = st.file_uploader(
                "Upload credentials.json", type=["json"], key="upload_creds"
            )
            if uploaded_cred is not None:
                cred_path = settings.client_secrets_resolved
                cred_path.write_bytes(uploaded_cred.getvalue())
                st.success("Saved credentials.json! Now click Authenticate below.")

            if settings.client_secrets_resolved.exists():
                if st.button("🚀 Authenticate via Browser", use_container_width=True):
                    try:
                        creds = get_google_credentials(
                            settings.client_secrets_resolved,
                            settings.token_file_resolved,
                            interactive=True,
                        )
                        if creds:
                            service.reconnect_services()
                            st.success("Authenticated successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Authentication failed: {e}")
            else:
                st.caption(
                    "Download OAuth Desktop credentials.json from Google Cloud Console and place it in this folder."
                )

    st.markdown("---")
    st.subheader("🤖 AI Resume Engine")
    if has_antigravity_ai:
        st.success("⚡ Local Antigravity AI Engine (Active)")
        st.caption("Extracting candidate skills & summaries using local IDE AI.")
    elif settings.gemini_api_key:
        st.success(f"☁️ Gemini API ({settings.gemini_model})")
    else:
        st.info("Deterministic Sample Parser")

    st.markdown("---")
    st.subheader("⚙️ Settings")
    override_email = st.text_input(
        "Test Recipient Override:",
        value=settings.demo_recipient_override or "",
        placeholder="your.email@gmail.com",
        help="All interview emails will be routed to this test address.",
    )
    if override_email != (settings.demo_recipient_override or ""):
        settings.demo_recipient_override = override_email.strip() if override_email.strip() else None

    sheet_id_input = st.text_input(
        "Google Spreadsheet ID:",
        value=settings.spreadsheet_id or "",
        placeholder="e.g. 1BxiMVs0XRA5nFM...",
    )
    if sheet_id_input != (settings.spreadsheet_id or ""):
        settings.spreadsheet_id = sheet_id_input.strip() if sheet_id_input.strip() else None
        if is_google_connected:
            service.reconnect_services()

    st.markdown("---")
    if st.button("🗑️ Reset All Data", use_container_width=True):
        db.reset_database(db_path)
        st.toast("Database cleared!")
        st.rerun()


# --- TOP DASHBOARD BANNER & METRICS ---
st.title("Automated Recruitment Intake & Outreach")

# Summary Metric Cards
counts = db.get_dashboard_counts(db_path)
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("Total Candidates", counts["total_candidates"])
with col_m2:
    st.metric("Awaiting Review", counts["pending_review"])
with col_m3:
    st.metric("Ready for Interview", counts["interview_ready"])
with col_m4:
    st.metric("Invitations Dispatched", counts["invitations_sent"])

st.markdown("---")

# --- INTAKE SCANNER BAR ---
st.subheader("📥 Step 1: Scan Gmail Inbox for Candidate CVs")

if not is_google_connected:
    st.warning("⚠️ **Your Gmail is not connected yet.** Link your account below or in the sidebar to read real CVs directly from your inbox.")
    conn_col1, conn_col2 = st.columns([3, 1])
    with conn_col1:
        st.info("💡 Place `credentials.json` from Google Cloud in this folder (or upload in sidebar) and run `python cli.py auth` to link your Gmail in 1 click.")
    with conn_col2:
        if settings.client_secrets_resolved.exists():
            if st.button("🔑 Connect Gmail Account", type="primary", use_container_width=True):
                try:
                    creds = get_google_credentials(
                        settings.client_secrets_resolved,
                        settings.token_file_resolved,
                        interactive=True,
                    )
                    if creds:
                        service.reconnect_services()
                        st.success("Connected to your Gmail!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Connection failed: {e}")

# Job Subject Filter & Instructions
search_col, btn_col1 = st.columns([3.8, 1.4])

with search_col:
    # Use session state for preset buttons
    if "job_subject_tag" not in st.session_state:
        st.session_state.job_subject_tag = "Job Application"

    tag_input = st.text_input(
        "🏷️ Job Subject Keyword / Tag (Emails containing this subject will be scanned):",
        value=st.session_state.job_subject_tag,
        help="Specify the keyword or tag you ask candidates to put in their email subject.",
        key="tag_input_field",
    )
    st.session_state.job_subject_tag = tag_input

    # Quick Preset Tags
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1:
        if st.button("📌 'Job Application'", key="preset_1"):
            st.session_state.job_subject_tag = "Job Application"
            st.rerun()
    with col_t2:
        if st.button("📌 'Application'", key="preset_2"):
            st.session_state.job_subject_tag = "Application"
            st.rerun()
    with col_t3:
        if st.button("📌 'CV / Resume'", key="preset_3"):
            st.session_state.job_subject_tag = "CV"
            st.rerun()
    with col_t4:
        if st.button("📌 All PDF Emails", key="preset_4"):
            st.session_state.job_subject_tag = ""
            st.rerun()

active_tag = st.session_state.job_subject_tag.strip()

with btn_col1:
    st.write("")
    st.write("")
    if st.button("🔍 Scan Gmail for CVs", type="primary", use_container_width=True):
        if not is_google_connected:
            st.error("Please connect your Google account first to scan your real Gmail inbox!")
        else:
            if active_tag:
                query = f'subject:"{active_tag}" has:attachment filename:pdf'
            else:
                query = "has:attachment filename:pdf"

            with st.spinner(f"Scanning Gmail for emails with query: `{query}`..."):
                stats = service.process_inbox(query=query, force_demo=False)
                st.success(
                    f"Scan complete! Received: {stats.get('received', 0)}, "
                    f"New Processed: {stats.get('processed', 0)}, Skipped (Already In Ledger): {stats.get('skipped', 0)}"
                )
                st.rerun()

# Candidate Instructions Box
if active_tag:
    st.info(
        f"📢 **Job Posting Instructions for Applicants:**\n\n"
        f"Ask candidates to email their CV to your Gmail with Subject: **`{active_tag} - [Candidate Name]`**\n\n"
        f"*(RecruitFlow will automatically filter out all your personal, bills, or bank emails and only process emails matching this subject!)*"
    )

st.markdown("---")

# --- TABS: CANDIDATE REVIEW & INTERVIEW OUTREACH ---
tab_review, tab_interview, tab_sheet = st.tabs([
    "📋 Step 2: Review Candidates & Make Decisions",
    "✉️ Step 3: Send Approved Interview Invitations",
    "📊 Step 4: Live Google Sheet / Local Tracker",
])

# -----------------------------------------------------------------------------
# TAB 1: REVIEW CANDIDATES & 1-CLICK DECISIONS
# -----------------------------------------------------------------------------
with tab_review:
    st.markdown("### Candidates Awaiting Review")
    st.caption("Review extracted qualifications and make instant 1-click decisions.")

    # Filter dropdown
    filter_choice = st.selectbox(
        "Filter by Status:",
        ["All Applicants", "Pending Review", "Needs Review", "Interview", "Hold", "Rejected"],
    )
    status_filter = None
    if filter_choice != "All Applicants":
        status_filter = CandidateStatus(filter_choice)

    candidates = db.get_all_candidates(db_path, status=status_filter)

    if not candidates:
        st.info("No candidates found in this view. Click 'Check Gmail Inbox' or 'Load Demo Resumes' above.")
    else:
        for cand in candidates:
            with st.container():
                st.markdown('<div class="candidate-card">', unsafe_allow_html=True)
                header_col, badge_col = st.columns([4, 1.5])
                with header_col:
                    st.markdown(f"### 👤 {cand.name or 'Applicant (Name Missing)'}")
                    st.markdown(f"**Email:** `{cand.email or 'No email provided'}` | **Resume File:** `{cand.attachment_filename}`")
                with badge_col:
                    if cand.status == CandidateStatus.INTERVIEW:
                        st.markdown('<span class="status-badge-interview">✅ INTERVIEW</span>', unsafe_allow_html=True)
                    elif cand.status == CandidateStatus.NEEDS_REVIEW:
                        st.markdown('<span class="status-badge-needs">⚠️ NEEDS REVIEW</span>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<span class="status-badge-review">⏳ {cand.status.value.upper()}</span>', unsafe_allow_html=True)

                if cand.status == CandidateStatus.NEEDS_REVIEW:
                    st.error(f"⚠️ **Why Needs Review?** {cand.processing_error or 'Scanned or unreadable document.'}")

                # AI Summary & Experience
                st.markdown("**AI Factual Summary:**")
                st.info(cand.short_summary or cand.experience_summary or "No summary extracted.")

                # Skills
                if cand.skills:
                    st.markdown("**Identified Skills:**")
                    skills_markup = "".join([f'<span class="skill-tag">{s}</span>' for s in cand.skills])
                    st.markdown(skills_markup, unsafe_allow_html=True)

                # Missing Info Alert
                if cand.missing_information:
                    st.markdown("**Missing Information:**")
                    missing_markup = "".join([f'<span class="missing-tag">{m}</span>' for m in cand.missing_information])
                    st.markdown(missing_markup, unsafe_allow_html=True)

                st.write("")
                # Quick 1-Click Action Buttons
                btn_c1, btn_c2, btn_c3, _ = st.columns([1.5, 1.2, 1.2, 2])
                with btn_c1:
                    if st.button("✅ Move to Interview", key=f"int_{cand.candidate_id}", use_container_width=True):
                        service.set_candidate_status(cand.candidate_id, CandidateStatus.INTERVIEW)
                        st.toast(f"Moved {cand.name} to Interview!")
                        st.rerun()
                with btn_c2:
                    if st.button("⏸️ Put on Hold", key=f"hld_{cand.candidate_id}", use_container_width=True):
                        service.set_candidate_status(cand.candidate_id, CandidateStatus.HOLD)
                        st.toast(f"Put {cand.name} on Hold.")
                        st.rerun()
                with btn_c3:
                    if st.button("❌ Reject", key=f"rej_{cand.candidate_id}", use_container_width=True):
                        service.set_candidate_status(cand.candidate_id, CandidateStatus.REJECTED)
                        st.toast(f"Marked {cand.name} as Rejected.")
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# TAB 2: APPROVED INTERVIEW OUTREACH (1-CLICK SEND)
# -----------------------------------------------------------------------------
with tab_interview:
    st.markdown("### Candidates Ready for Interview Outreach")
    st.caption("Review the personalized email invitation with scheduling link and dispatch.")

    interview_cands = db.get_all_candidates(db_path, status=CandidateStatus.INTERVIEW)

    if not interview_cands:
        st.info("No candidates are currently marked for 'Interview'. In Step 2, click '✅ Move to Interview' on any candidate.")
    else:
        for cand in interview_cands:
            preview = service.prepare_interview_email_preview(cand.candidate_id)
            if not preview:
                continue

            with st.container():
                st.markdown('<div class="candidate-card">', unsafe_allow_html=True)
                st.markdown(f"### ✉️ Interview Invitation for **{cand.name}**")

                if cand.interview_email_sent_at:
                    st.success(
                        f"✅ **Invitation already dispatched** at `{cand.interview_email_sent_at}`! "
                        "Duplicate sending is safely blocked."
                    )
                else:
                    if preview.is_override:
                        st.warning(f"⚠️ **Test Mode Active:** Email will be sent to your override address: `{preview.effective_recipient}` (Applicant email was `{preview.recipient}`).")
                    else:
                        st.markdown(f"**Recipient:** `{preview.recipient}`")

                    st.markdown(f"**Subject:** `{preview.subject}`")
                    st.markdown(f"**Scheduling Link:** [{preview.scheduling_url}]({preview.scheduling_url})")

                    with st.expander("👁️ View Full Rendered Email"):
                        st.markdown(f'<div class="email-box">{preview.body_html}</div>', unsafe_allow_html=True)

                    st.write("")
                    col_send, col_status = st.columns([2, 3])
                    with col_send:
                        send_label = (
                            "🚀 Send Real Gmail Invitation"
                            if (is_google_connected and settings.enable_email_send)
                            else "📝 Record Simulated Send in Outbox"
                        )
                        if st.button(send_label, key=f"send_btn_{cand.candidate_id}", type="primary", use_container_width=True):
                            with st.spinner("Dispatching invitation..."):
                                success, msg = service.send_interview_invitation(
                                    cand.candidate_id, explicit_approval=True
                                )
                                if success:
                                    st.success(msg)
                                    st.balloons()
                                    st.rerun()
                                else:
                                    st.error(f"Send failed: {msg}")

                st.markdown('</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# TAB 3: LIVE TRACKER & GOOGLE SHEETS
# -----------------------------------------------------------------------------
with tab_sheet:
    st.markdown("### Candidate Tracking Ledger")

    if is_google_connected and settings.spreadsheet_id:
        st.success(f"🟢 Synchronized Live with Google Sheet ID: `{settings.spreadsheet_id}` (Tab: `{settings.sheet_name}`)")
    else:
        st.info("📋 Local Ledger View (Connect Google Account in sidebar to sync live with Google Sheets).")

    all_cands = db.get_all_candidates(db_path)
    if all_cands:
        rows = [c.to_sheet_row() for c in all_cands]
        df = pd.DataFrame(rows, columns=CandidateRecord.sheet_headers())
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("No candidates in ledger yet.")
