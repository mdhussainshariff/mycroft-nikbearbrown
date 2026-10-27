"""
WHAT THIS FILE DOES: Unit tests for explain.py — proves the explanation text
reflects the plan's actual vehicle/date/time, handles missing date/time
gracefully, and always passes the original action_plan through unmodified.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from explain import generate_explanation


def test_explanation_includes_vehicle_date_and_time():
    plan = {"action": "schedule_test_drive", "vehicle_mention": "camry", "requested_date": "2026-10-05", "requested_time": "2pm"}
    result = generate_explanation(plan)
    assert "Camry" in result["explanation_text"]
    assert "2026-10-05" in result["explanation_text"]
    assert "2pm" in result["explanation_text"]
    assert result["action_plan"] == plan


def test_explanation_handles_missing_date_and_time():
    plan = {"action": "schedule_test_drive", "vehicle_mention": "civic", "requested_date": None, "requested_time": None}
    result = generate_explanation(plan)
    assert "Civic" in result["explanation_text"]
    assert "to be confirmed" in result["explanation_text"]


def test_explanation_passes_plan_through_unmodified():
    plan = {"action": "schedule_test_drive", "vehicle_mention": "accord", "requested_date": "2026-11-01", "requested_time": None}
    result = generate_explanation(plan)
    assert result["action_plan"] is plan


if __name__ == "__main__":
    test_explanation_includes_vehicle_date_and_time()
    test_explanation_handles_missing_date_and_time()
    test_explanation_passes_plan_through_unmodified()
    print("All test_explain.py tests passed.")
