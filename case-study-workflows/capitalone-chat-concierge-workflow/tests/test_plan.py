"""
WHAT THIS FILE DOES: Unit tests for plan.py — proves the feasibility check
fires on blackout dates, non-operating days, and out-of-hours times, and
that a feasible request produces a correctly-shaped action plan.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plan import build_plan

CONSTRAINTS = {
    "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    "operating_hours": {"open": "09:00", "close": "18:00"},
    "blackout_dates": ["2026-12-25", "2026-01-01"],
}


def test_feasible_request_produces_plan():
    parsed = {"vehicle_mention": "camry", "requested_date": "2026-10-05", "requested_time": "2pm"}
    result = build_plan(parsed, CONSTRAINTS)
    assert "status" not in result
    assert result["action"] == "schedule_test_drive"
    assert result["vehicle_mention"] == "camry"


def test_blackout_date_halts():
    parsed = {"vehicle_mention": "camry", "requested_date": "2026-12-25", "requested_time": "2pm"}
    result = build_plan(parsed, CONSTRAINTS)
    assert result["status"] == "halted"
    assert result["stage"] == "plan"
    assert result["reason"] == "infeasible_against_business_rules"


def test_non_operating_day_halts():
    # 2026-10-04 is a Sunday
    parsed = {"vehicle_mention": "camry", "requested_date": "2026-10-04", "requested_time": "2pm"}
    result = build_plan(parsed, CONSTRAINTS)
    assert result["status"] == "halted"
    assert result["reason"] == "infeasible_against_business_rules"


def test_out_of_hours_time_halts():
    parsed = {"vehicle_mention": "camry", "requested_date": "2026-10-05", "requested_time": "8pm"}
    result = build_plan(parsed, CONSTRAINTS)
    assert result["status"] == "halted"
    assert result["reason"] == "infeasible_against_business_rules"


def test_request_with_no_date_or_time_is_feasible_by_default():
    parsed = {"vehicle_mention": "civic", "requested_date": None, "requested_time": None}
    result = build_plan(parsed, CONSTRAINTS)
    assert "status" not in result
    assert result["action"] == "schedule_test_drive"


if __name__ == "__main__":
    test_feasible_request_produces_plan()
    test_blackout_date_halts()
    test_non_operating_day_halts()
    test_out_of_hours_time_halts()
    test_request_with_no_date_or_time_is_feasible_by_default()
    print("All test_plan.py tests passed.")
