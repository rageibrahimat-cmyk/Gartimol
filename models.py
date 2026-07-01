"""
SQLAlchemy models.

Per §2 of the architecture spec, TrustScoring owns only `trust_score_snapshot`.
PlanGoal, ActivityEvent, and Alert are owned by upstream contexts (SeasonalContext
and Alerting/Ledger) — they're modeled here as read-only reflections so this
service can query them, per the MVP data model in Gartimol_MVP_Scope_v1.md §5.
This service must never write to those tables.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# --- Owned by this context ---

class TrustScoreSnapshotORM(Base):
    __tablename__ = "trust_score_snapshot"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_score_range"),
        Index("idx_trust_score_user_time", "user_id", "computed_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    score = Column(Float, nullable=False)
    plan_adherence = Column(Float, nullable=True)
    action_completion = Column(Float, nullable=True)
    computed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    inputs_snapshot = Column(JSONB, nullable=False)


# --- Read-only reflections of upstream-owned tables (per MVP §5) ---
# Not managed by this service's migrations; included so the router can
# query them without entangling this module with Alert/Ledger logic.

class PlanGoalORM(Base):
    __tablename__ = "plan_goal"
    __table_args__ = {"info": {"owned_by": "SeasonalContext"}}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    category = Column(String, nullable=False)
    target_value = Column(Float, nullable=False)
    declared_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ActivityEventORM(Base):
    __tablename__ = "activity_event"
    __table_args__ = {"info": {"owned_by": "Ledger"}}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    category = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    source = Column(String, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)


class AlertORM(Base):
    __tablename__ = "alert"
    __table_args__ = {"info": {"owned_by": "Alerting"}}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    rule_id = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String, nullable=False)  # open | actioned | dismissed
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actioned_at = Column(DateTime(timezone=True), nullable=True)
