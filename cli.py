"""
Command Line Interface for RecruitFlow.
Provides operations to generate samples, process intake cycles, run background poller,
inspect system state, and reset demo data.
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from recruitflow.config import get_settings
from recruitflow.workflow import WorkflowService
from recruitflow import db
from generate_samples import generate_all_samples

# Setup clean CLI logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("recruitflow.cli")


def cmd_generate_samples(args: argparse.Namespace) -> None:
    """Generate 3 synthetic CV PDFs."""
    print("==================================================")
    print("Generating Synthetic Candidate Resumes...")
    print("==================================================")
    generate_all_samples()
    print("Done. Sample CVs are ready in data/sample_cvs/")


def cmd_process_once(args: argparse.Namespace) -> None:
    """Execute a single intake cycle."""
    settings = get_settings()
    print("==================================================")
    print(f"Executing RecruitFlow Intake Cycle (DEMO_MODE={settings.demo_mode})")
    print("==================================================")
    service = WorkflowService(settings)
    stats = service.process_inbox()
    print("\nIntake Summary:")
    print(f"  • Attachments Received: {stats.get('received', 0)}")
    print(f"  • Processed / Extracted: {stats.get('processed', 0)}")
    print(f"  • Skipped (Deduplicated): {stats.get('skipped', 0)}")
    print(f"  • Errors / Failures:      {stats.get('errors', 0)}")
    print("\nCurrent Ledger Status:")
    cmd_status(args)


def cmd_poll_worker(args: argparse.Namespace) -> None:
    """Run continuous polling worker with graceful termination."""
    settings = get_settings()
    interval = args.interval if args.interval is not None else settings.poll_interval_seconds

    print("==================================================")
    print(f"Starting RecruitFlow Polling Worker (Interval: {interval}s)")
    print(f"Mode: {'DEMO MODE (Simulated)' if settings.demo_mode else 'LIVE GOOGLE CLOUD MODE'}")
    print("Press Ctrl+C to stop gracefully.")
    print("==================================================")

    running = True

    def handle_shutdown(signum, frame):
        nonlocal running
        print("\nShutdown signal received. Stopping worker safely...")
        running = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    service = WorkflowService(settings)

    while running:
        try:
            logger.info("Executing periodic intake cycle...")
            stats = service.process_inbox()
            logger.info(f"Cycle completed. Processed: {stats.get('processed', 0)}, Skipped: {stats.get('skipped', 0)}")
        except Exception as e:
            logger.error(f"Worker encountered unexpected error: {e}", exc_info=True)

        # Sleep in small increments for prompt responsiveness to SIGINT
        for _ in range(int(interval)):
            if not running:
                break
            time.sleep(1)

    print("RecruitFlow Worker shutdown cleanly.")


def cmd_status(args: argparse.Namespace) -> None:
    """Print current SQLite processing ledger status and candidate list."""
    settings = get_settings()
    db_path = settings.db_path_resolved
    db.init_db(db_path)

    counts = db.get_dashboard_counts(db_path)
    candidates = db.get_all_candidates(db_path)

    print("\n--- RECRUITFLOW SYSTEM STATUS ---")
    print(f"Database: {db_path}")
    print(f"Total Processed Attachments : {counts['total_attachments']}")
    print(f"Total Candidate Records     : {counts['total_candidates']}")
    print(f"  - Pending Review          : {counts['pending_review']}")
    print(f"  - Needs Review            : {counts['needs_review']}")
    print(f"  - Interview Ready         : {counts['interview_ready']}")
    print(f"  - Invitations Sent        : {counts['invitations_sent']}")
    print("---------------------------------")

    if candidates:
        print("\nCandidates in Ledger:")
        header = f"{'ID':<15} | {'Name':<18} | {'Email':<25} | {'Status':<16} | {'Sent At'}"
        print(header)
        print("-" * len(header))
        for c in candidates:
            sent_str = c.interview_email_sent_at[:16] if c.interview_email_sent_at else "Not sent"
            print(f"{c.candidate_id:<15} | {(c.name or 'N/A'):<18} | {(c.email or 'N/A'):<25} | {c.status.value:<16} | {sent_str}")
    else:
        print("\nNo candidates in database yet. Run `python cli.py process-once`.")


def cmd_auth(args: argparse.Namespace) -> None:
    """Connect Google Account via OAuth Desktop Flow."""
    settings = get_settings()
    print("==================================================")
    print("Connecting Google Account (Gmail & Sheets OAuth)...")
    print("==================================================")
    from recruitflow.auth import get_google_credentials
    try:
        creds = get_google_credentials(
            settings.client_secrets_resolved,
            settings.token_file_resolved,
            interactive=True,
        )
        if creds:
            print("\n[SUCCESS] Google Account connected successfully! token.json saved.")
            print("Now RecruitFlow can actively fetch real CVs from your Gmail inbox.")
    except Exception as e:
        print(f"\n[ERROR] Authentication failed: {e}")


def cmd_reset_demo(args: argparse.Namespace) -> None:
    """Reset the SQLite database for a clean demo run."""
    settings = get_settings()
    db_path = settings.db_path_resolved
    db.init_db(db_path)
    db.reset_database(db_path)
    print(f"Successfully cleared all candidate records, processed attachments, and outbox logs from {db_path}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RecruitFlow: Automated Recruitment Automation CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # auth
    p_auth = subparsers.add_parser("auth", help="Connect personal Google account (Gmail & Sheets)")
    p_auth.set_defaults(func=cmd_auth)

    # generate-samples
    p_gen = subparsers.add_parser("generate-samples", help="Generate 3 synthetic CV PDFs in data/sample_cvs")
    p_gen.set_defaults(func=cmd_generate_samples)

    # process-once
    p_proc = subparsers.add_parser("process-once", help="Run a single intake, extraction, and sync cycle")
    p_proc.set_defaults(func=cmd_process_once)

    # poll-worker
    p_poll = subparsers.add_parser("poll-worker", help="Start continuous polling background worker")
    p_poll.add_argument("--interval", type=int, default=None, help="Poll interval in seconds")
    p_poll.set_defaults(func=cmd_poll_worker)

    # status
    p_stat = subparsers.add_parser("status", help="Display candidate summary and ledger counts")
    p_stat.set_defaults(func=cmd_status)

    # reset-demo
    p_reset = subparsers.add_parser("reset-demo", help="Clear all database records for demo reset")
    p_reset.set_defaults(func=cmd_reset_demo)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
