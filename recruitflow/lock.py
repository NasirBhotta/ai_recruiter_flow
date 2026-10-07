"""
Process locking mechanism to prevent overlapping worker runs.
Uses SQLite worker_locks table with process PID and heartbeat expiration.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timezone
import logging

from recruitflow.db import get_connection

logger = logging.getLogger(__name__)


class WorkerLock:
    """
    Context manager to ensure only one worker execution runs at a time.
    Stale locks (> ttl_seconds) are automatically superseded.
    """

    def __init__(
        self,
        db_path: str | Path,
        lock_name: str = "recruitflow_intake_worker",
        ttl_seconds: int = 300,
    ):
        self.db_path = db_path
        self.lock_name = lock_name
        self.ttl_seconds = ttl_seconds
        self.acquired = False
        self.owner_info = f"PID:{os.getpid()}_{time.time()}"

    def __enter__(self) -> bool:
        self.acquired = self.acquire()
        return self.acquired

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.acquired:
            self.release()

    def acquire(self) -> bool:
        """Attempt to acquire exclusive worker lock."""
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT acquired_at, owner_info FROM worker_locks WHERE lock_name = ?",
                (self.lock_name,),
            ).fetchone()

            if row:
                acquired_at_iso = row["acquired_at"]
                try:
                    acquired_dt = datetime.fromisoformat(acquired_at_iso)
                    age = (datetime.now(timezone.utc) - acquired_dt).total_seconds()
                except Exception:
                    age = 999999

                if age < self.ttl_seconds:
                    logger.warning(
                        f"Worker lock '{self.lock_name}' is currently held by {row['owner_info']} (age: {age:.1f}s)."
                    )
                    return False
                else:
                    logger.info(
                        f"Worker lock '{self.lock_name}' expired (age: {age:.1f}s). Overriding stale lock."
                    )

            # Insert or replace lock
            cursor.execute(
                """
                INSERT OR REPLACE INTO worker_locks (lock_name, acquired_at, owner_info)
                VALUES (?, ?, ?)
                """,
                (self.lock_name, now_iso, self.owner_info),
            )
            conn.commit()
            return True

    def release(self) -> None:
        """Release lock if owned by this process."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                "DELETE FROM worker_locks WHERE lock_name = ? AND owner_info = ?",
                (self.lock_name, self.owner_info),
            )
            conn.commit()
            self.acquired = False
