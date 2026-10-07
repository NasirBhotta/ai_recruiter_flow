# RecruitFlow: 90-Second Demo Recording Script

**Target Duration:** 90 Seconds  
**Resolution:** 1080p (1920x1080), 60 FPS  
**Voiceover Tone:** Confident, technical, articulate senior engineer  
**Visual Tool:** Streamlit Web UI + Windows PowerShell terminal  

---

## Timeline & Scene Breakdown

### [00:00 - 00:15] Scene 1: The Problem & Architecture Overview
* **Visual:**
  - Split screen or slide transitioning to Streamlit Dashboard.
  - Highlight top KPI cards: `Total Attachments: 0`, `Candidates Ingested: 0`.
* **Voiceover:**
  > "Recruiting teams lose hundreds of hours sifting through resumes and manually tracking applicants across disparate spreadsheets and email threads. 
  > This is **RecruitFlow**—a human-in-the-loop recruitment automation engine. It connects Gmail intake, local PDF parsing, Gemini structured extraction, and Google Sheets, while keeping strict human oversight on every interview invitation."

---

### [00:15 - 00:35] Scene 2: One-Click Ingestion & Local Parsing
* **Visual:**
  - Cursor clicks **"🚀 Run Intake Poller Now"** in the sidebar.
  - A subtle spinner appears; candidate records instantly populate the table.
  - Top metric cards animate: `Total Attachments: 3`, `Pending Review: 2`, `Needs Review: 1`.
* **Voiceover:**
  > "In Demo Mode, RecruitFlow runs completely offline without external credentials. When we trigger the poller, it reads incoming application PDFs, enforces size limits, and parses text locally.
  > Notice the status counters: two candidates passed extraction into 'Pending Review', while an unreadable scanned PDF was instantly flagged and routed to 'Needs Review'."

---

### [00:35 - 00:55] Scene 3: Gemini Structured Summary & Safety Verification
* **Visual:**
  - Click on **Alice Chen** in the candidate inspector.
  - Highlight the Gemini extraction cards:
    - Factual summary of 7+ years backend experience.
    - Skill pills: `Python`, `FastAPI`, `PostgreSQL`, `Docker`, `Kubernetes`.
  - Now click on **Bob Miller**:
    - Highlight the red/amber chips under *Missing Information*: `[phone number]`, `[university degree]`.
  - Point out that no hallucinatory qualifications or hiring acceptance scores were generated.
* **Voiceover:**
  > "RecruitFlow treats resume text strictly as untrusted data. Using Gemini's structured output schema, it extracts verifiable facts—skills, stated roles, and career highlights. 
  > Crucially, missing information remains null. Notice that Bob Miller's missing phone number and degree are explicitly flagged rather than hallucinated, and no arbitrary acceptance scores are invented."

---

### [00:55 - 01:15] Scene 4: Human Review & Recruiter Approval
* **Visual:**
  - In Alice Chen's review controls on the right, change status from `Pending Review` to `Interview`.
  - Click **"💾 Save Status Update"**.
  - Navigate to the **"✉️ Interview Outreach & Approval"** tab.
  - Select Alice Chen. Show the live **Email Preview** box with the dynamic `SCHEDULING_URL` link.
  - Show the unchecked safety checkbox: the Send button is disabled!
  - Check the approval box: `[x] I confirm that I have reviewed Alice Chen's profile...`
  - Click **"📝 Record Simulated Send in Outbox"** (or Dispatch Live Email).
  - Balloons celebrate the send!
* **Voiceover:**
  > "Safety is built into the core workflow: no email can ever be dispatched automatically. 
  > A recruiter must manually move the candidate to 'Interview' status, review the rendered scheduling template, and provide explicit checkbox approval. 
  > Once approved, the invitation is logged to our durable ledger."

---

### [01:15 - 01:30] Scene 5: Outbox Audit Trail, Deduplication & Google Sheets Sync
* **Visual:**
  - Switch to **"📬 Outbox Audit Trail"** tab: show the logged message to `alice.chen@example.com` with timestamp.
  - Switch to **"📊 Google Sheet Sync Ledger"** tab: show all 11 columns in sync with candidate statuses.
  - Attempt to click Send again or run poller: show that duplicate send and duplicate intake are strictly rejected.
* **Voiceover:**
  > "Every dispatch is durably audited in our outbox, and candidate rows stay synchronized with our Google Sheet. Idempotent SQLite ledgers prevent duplicate email sends and redundant intake processing. 
  > Full code, offline test suite, and one-command setup are available in the repository."

---

## Recording Checklist
1. Launch app: `streamlit run app.py`
2. Reset DB before starting: click `🗑️ Reset DB` to start with 0 candidates.
3. Have browser open at `http://localhost:8501`.
4. Run through script steps cleanly in sequence.
