"""
Tests for the null-handling logic in §3.3 of the architecture spec.

Per the handoff notes (§8): "Write unit tests against the null-handling
cases in §3.3 first — that's the logic most likely to be silently wrong
in a way that damages user trust." These run before any DB/API code.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.schemas import ActivityEvent, Alert, PlanGoal
from app.scoring import (
    compute_action_completion,
    compute_plan_adherence,
    compute_trust_score,
)

NOW = datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)
PERIOD_START = NOW - timedelta(days=30)


# ---- §3.1 Plan Adherence edge cases ----

def test_zero_goals_returns_none_not_zero():
    """Zero declared goals must be None (excluded), never a scored 0."""
    result = compute_plan_adherence([], [], PERIOD_START, NOW)
    assert result is None


def test_plan_adherence_caps_at_100_for_overachievement():
    goals = [PlanGoal(category="savings", target_value=100)]
    events = [ActivityEvent(category="savings", value=250, occurred_at=NOW)]
    result = compute_plan_adherence(goals, events, PERIOD_START, NOW)
    assert result == 100.0  # MIN(actual/target, 1.0) — never exceeds 100


def test_plan_adherence_averages_across_multiple_goals():
    goals = [
        PlanGoal(category="savings", target_value=100),
        PlanGoal(category="fitness", target_value=10),
    ]
    events = [
        ActivityEvent(category="savings", value=50, occurred_at=NOW),  # 50%
        ActivityEvent(category="fitness", value=10, occurred_at=NOW),  # 100%
    ]
    result = compute_plan_adherence(goals, events, PERIOD_START, NOW)
    assert result == pytest.approx(75.0)


def test_plan_adherence_ignores_events_outside_period():
    goals = [PlanGoal(category="savings", target_value=100)]
    events = [
        ActivityEvent(category="savings", value=100, occurred_at=PERIOD_START - timedelta(days=1))
    ]
    result = compute_plan_adherence(goals, events, PERIOD_START, NOW)
    assert result == 0.0


def test_plan_adherence_ignores_events_in_other_categories():
    goals = [PlanGoal(category="savings", target_value=100)]
    events = [ActivityEvent(category="fitness", value=999, occurred_at=NOW)]
    result = compute_plan_adherence(goals, events, PERIOD_START, NOW)
    assert result == 0.0


# ---- §3.2 Action Completion edge cases ----

def test_zero_alerts_in_window_returns_none_not_zero():
    """Zero alerts must be None (excluded), never scored as 0% or 100%."""
    result = compute_action_completion([], NOW)
    assert result is None


def test_action_completion_ignores_alerts_outside_window():
    alerts = [
        Alert(status="actioned", created_at=NOW - timedelta(days=8)),  # outside 7-day window
    ]
    result = compute_action_completion(alerts, NOW)
    assert result is None


def test_action_completion_rate_basic():
    alerts = [
        Alert(status="actioned", created_at=NOW - timedelta(days=1)),
        Alert(status="actioned", created_at=NOW - timedelta(days=2)),
        Alert(status="dismissed", created_at=NOW - timedelta(days=3)),
        Alert(status="open", created_at=NOW - timedelta(days=4)),
    ]
    result = compute_action_completion(alerts, NOW)
    assert result == pytest.approx(50.0)


# ---- §3.3 Final score combination logic ----

def test_both_present_uses_weighted_formula():
    goals = [PlanGoal(category="savings", target_value=100)]
    events = [ActivityEvent(category="savings", value=80, occurred_at=NOW)]  # 80%
    alerts = [
        Alert(status="actioned", created_at=NOW - timedelta(days=1)),
        Alert(status="open", created_at=NOW - timedelta(days=2)),
    ]  # 50%
    result = compute_trust_score(goals, events, alerts, now=NOW)
    # 0.6*80 + 0.4*50 = 48 + 20 = 68
    assert result.score == pytest.approx(68.0)
    assert result.insufficient_data is False


def test_only_plan_adherence_present_falls_back_to_it_alone():
    goals = [PlanGoal(category="savings", target_value=100)]
    events = [ActivityEvent(category="savings", value=80, occurred_at=NOW)]
    result = compute_trust_score(goals, events, [], now=NOW)
    assert result.score == pytest.approx(80.0)
    assert result.action_completion is None
    assert result.insufficient_data is False


def test_only_action_completion_present_falls_back_to_it_alone():
    alerts = [Alert(status="actioned", created_at=NOW - timedelta(days=1))]
    result = compute_trust_score([], [], alerts, now=NOW)
    assert result.score == pytest.approx(100.0)
    assert result.plan_adherence is None
    assert result.insufficient_data is False


def test_neither_present_returns_none_never_fakes_a_number():
    """The critical case: no goals, no alerts -> score must be None, not 0."""
    result = compute_trust_score([], [], [], now=NOW)
    assert result.score is None
    assert result.insufficient_data is True
    assert "not enough data" in result.explanation.lower()


def test_explanation_reflects_actual_numbers_not_canned_text():
    goals = [PlanGoal(category="savings", target_value=100)]
    events = [ActivityEvent(category="savings", value=82, occurred_at=NOW)]
    alerts = [
        Alert(status="actioned", created_at=NOW - timedelta(days=1)),
        Alert(status="actioned", created_at=NOW - timedelta(days=2)),
        Alert(status="open", created_at=NOW - timedelta(days=3)),
        Alert(status="open", created_at=NOW - timedelta(days=4)),
    ]  # 50%
    result = compute_trust_score(goals, events, alerts, now=NOW)
    assert "82.0%" in result.explanation
    assert "50.0%" in result.explanation
