"""
API contract per §4 of the architecture spec.

This is a standalone router, mounted into the main app but never importing
from Alert or Ledger service modules directly — it only reads their data
via the ORM models in app.models, per the bounded-context boundary called
out in the handoff notes (§8).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import require_user_or_admin
from app.db import get_db
from app.models import ActivityEventORM, AlertORM, PlanGoalORM, TrustScoreSnapshotORM
from app.schemas import (
    ActivityEvent,
    Alert,
    HistoryPoint,
    InsufficientDataResponse,
    PlanGoal,
    RecomputeQueuedResponse,
    TrustScoreBreakdown,
    TrustScoreResponse,
)
from app.scoring import compute_trust_score

router = APIRouter(prefix="/v1/trust-score", tags=["trust-score"])


def _load_inputs(db: Session, user_id: UUID):
    """Read-only queries against upstream-owned tables (§1: consumer, not owner)."""
    goals = [
        PlanGoal(category=g.category, target_value=g.target_value)
        for g in db.query(PlanGoalORM).filter(PlanGoalORM.user_id == user_id).all()
    ]
    events = [
        ActivityEvent(category=e.category, value=e.value, occurred_at=e.occurred_at)
        for e in db.query(ActivityEventORM).filter(ActivityEventORM.user_id == user_id).all()
    ]
    alerts = [
        Alert(status=a.status, created_at=a.created_at)
        for a in db.query(AlertORM).filter(AlertORM.user_id == user_id).all()
    ]
    return goals, events, alerts


def _persist_snapshot(db: Session, user_id: UUID, result, now: datetime) -> TrustScoreSnapshotORM:
    """Always writes a snapshot, including insufficient-data states, for the audit trail (§6)."""
    snapshot = TrustScoreSnapshotORM(
        user_id=user_id,
        score=result.score if result.score is not None else 0.0,
        plan_adherence=result.plan_adherence,
        action_completion=result.action_completion,
        computed_at=now,
        inputs_snapshot={
            "plan_adherence": result.plan_adherence,
            "action_completion": result.action_completion,
            "insufficient_data": result.insufficient_data,
        },
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.get(
    "/{user_id}",
    response_model=Union[TrustScoreResponse, InsufficientDataResponse],
)
def get_trust_score(
    user_id: UUID,
    db: Session = Depends(get_db),
    _auth=Depends(require_user_or_admin),
):
    now = datetime.now(timezone.utc)
    goals, events, alerts = _load_inputs(db, user_id)
    result = compute_trust_score(goals, events, alerts, now=now)

    if result.insufficient_data:
        return Response(
            status_code=status.HTTP_204_NO_CONTENT,
        )

    return TrustScoreResponse(
        score=round(result.score, 1),
        computed_at=now,
        breakdown=TrustScoreBreakdown(
            plan_adherence=result.plan_adherence,
            action_completion=result.action_completion,
        ),
        explanation=result.explanation,
    )


@router.get("/{user_id}/history", response_model=List[HistoryPoint])
def get_trust_score_history(
    user_id: UUID,
    days: int = 30,
    db: Session = Depends(get_db),
    _auth=Depends(require_user_or_admin),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(TrustScoreSnapshotORM)
        .filter(TrustScoreSnapshotORM.user_id == user_id)
        .filter(TrustScoreSnapshotORM.computed_at >= cutoff)
        .order_by(TrustScoreSnapshotORM.computed_at.asc())
        .all()
    )
    return [HistoryPoint(score=r.score, computed_at=r.computed_at) for r in rows]


@router.post(
    "/{user_id}/recompute",
    response_model=RecomputeQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def recompute_trust_score(
    user_id: UUID,
    db: Session = Depends(get_db),
    _auth=Depends(require_user_or_admin),
):
    """
    Synchronous recompute-and-persist for MVP (no task queue yet, per §5:
    don't build event-driven infra before you have the user volume to
    justify it). Swap for a background task/queue in v2 without changing
    this response contract.
    """
    now = datetime.now(timezone.utc)
    goals, events, alerts = _load_inputs(db, user_id)
    result = compute_trust_score(goals, events, alerts, now=now)
    _persist_snapshot(db, user_id, result, now)
    return RecomputeQueuedResponse()
