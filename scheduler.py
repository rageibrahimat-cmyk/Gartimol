"""
Scheduled recompute, per §5: "MVP: scheduled recompute every 15 minutes
per active user (cron job / background worker)."

Run standalone: `python -m app.scheduler`
This intentionally does NOT touch Kafka/event sourcing (§5, §7) —
it's a plain polling loop, sufficient for MVP user volume.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from app.db import SessionLocal
from app.models import PlanGoalORM
from app.router import _load_inputs, _persist_snapshot
from app.scoring import compute_trust_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trust_score_scheduler")

RECOMPUTE_INTERVAL_SECONDS = 15 * 60


def _active_user_ids(db) -> list[UUID]:
    """
    MVP definition of "active": has at least one declared PlanGoal.
    Refine this once you have a real activity/last-seen signal.
    """
    rows = db.query(PlanGoalORM.user_id).distinct().all()
    return [r[0] for r in rows]


def run_once() -> None:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        user_ids = _active_user_ids(db)
        logger.info("Recomputing Trust Score for %d active users", len(user_ids))
        for user_id in user_ids:
            goals, events, alerts = _load_inputs(db, user_id)
            result = compute_trust_score(goals, events, alerts, now=now)
            _persist_snapshot(db, user_id, result, now)
    finally:
        db.close()


def run_forever() -> None:
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("Scheduled recompute failed")
        time.sleep(RECOMPUTE_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
