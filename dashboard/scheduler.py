"""APScheduler integration — schedule posts to publish at a future time.

Uses the existing dashboard DB and Manager for publishing. APScheduler
stores its own job metadata in a separate SQLite file so it never
collides with the post table.

Usage:
    from dashboard import scheduler
    scheduler.start()                         # call once at app boot
    scheduler.schedule_post(post_id, run_at)  # queue a post
    scheduler.cancel_post(post_id)            # cancel before it fires
    scheduler.list_jobs()                     # see what's pending
    scheduler.shutdown()                      # clean stop
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from . import db

log = logging.getLogger("social-engine.scheduler")

# Job metadata lives in its own file — never touches dashboard.db
JOBS_DIR = Path.home() / ".social-auto-engine"
JOBS_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DB = JOBS_DIR / "scheduler_jobs.db"

_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    """Lazy-init the scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            jobstores={
                "default": SQLAlchemyJobStore(
                    url=f"sqlite:///{JOBS_DB.as_posix()}"
                )
            },
            timezone=timezone.utc,
        )
    return _scheduler


def start() -> None:
    """Start the scheduler. Safe to call multiple times."""
    s = get_scheduler()
    if not s.running:
        s.start()
        log.info("Scheduler started — jobs_db=%s", JOBS_DB)


def shutdown(wait: bool = False) -> None:
    """Stop the scheduler gracefully."""
    s = get_scheduler()
    if s.running:
        s.shutdown(wait=wait)
        log.info("Scheduler stopped")


# ---------------------------------------------------------------------------
# Job function — this is what APScheduler calls when a post is due
# ---------------------------------------------------------------------------

def _publish_scheduled_post(post_id: int) -> None:
    """Called by APScheduler when a scheduled post's time arrives.

    Imports the publish function from app.py to reuse the exact same
    publishing logic (platform dispatch, error handling, DB updates).
    """
    post = db.get_post(post_id)
    if not post:
        log.warning("Scheduled post #%s not found — skipping", post_id)
        return

    if post["status"] != "scheduled":
        log.info(
            "Post #%s is '%s', not 'scheduled' — skipping",
            post_id, post["status"],
        )
        return

    # Mark as pending so the publish function can process it
    db.update_post(post_id, status="pending")

    # Import here to avoid circular imports
    from .app import _publish_post

    _publish_post(post)
    refreshed = db.get_post(post_id)
    status = refreshed["status"] if refreshed else "unknown"
    log.info("Scheduled post #%s → %s", post_id, status)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def schedule_post(post_id: int, run_at: datetime) -> str:
    """Schedule a post to publish at a specific time. Returns the job ID."""
    s = get_scheduler()
    job_id = f"post-{post_id}"

    # Ensure run_at is UTC-aware
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)

    s.add_job(
        _publish_scheduled_post,
        trigger="date",
        run_date=run_at,
        args=[post_id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300,  # 5 min grace for missed jobs
    )

    # Update the post record
    db.update_post(
        post_id,
        status="scheduled",
        scheduled_for=run_at.isoformat(),
    )

    log.info("Post #%s scheduled for %s (job=%s)", post_id, run_at, job_id)
    return job_id


def cancel_post(post_id: int) -> bool:
    """Cancel a scheduled post. Returns True if the job was found and removed."""
    s = get_scheduler()
    job_id = f"post-{post_id}"
    try:
        s.remove_job(job_id)
        db.update_post(
            post_id,
            status="pending",
            scheduled_for=None,
        )
        log.info("Cancelled scheduled post #%s", post_id)
        return True
    except Exception as e:
        log.info("Cancel post #%s: job not found (%s)", post_id, e)
        return False


def list_jobs() -> list[dict]:
    """Return all pending scheduled jobs."""
    s = get_scheduler()
    return [
        {
            "id": j.id,
            "post_id": j.args[0] if j.args else None,
            "next_run_time": (
                j.next_run_time.isoformat() if j.next_run_time else None
            ),
        }
        for j in s.get_jobs()
    ]
