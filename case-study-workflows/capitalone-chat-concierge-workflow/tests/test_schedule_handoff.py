"""
WHAT THIS FILE DOES: Unit tests for schedule_handoff.py — proves it calls
mock_dealer_crm correctly (spy-verified), returns the locked
scheduling_complete status shape, and degrades gracefully (not a modeled
halt) when a vehicle mention has no matching CRM record.
"""

import sys
import os
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from schedule_handoff import complete_scheduling


def test_complete_scheduling_returns_locked_status_shape():
    explanation_result = {
        "explanation_text": "Your test drive for the Camry is planned on 2026-10-05 at 2pm.",
        "action_plan": {"action": "schedule_test_drive", "vehicle_mention": "camry", "requested_date": "2026-10-05", "requested_time": "2pm"},
    }
    result = complete_scheduling(explanation_result)
    assert result["status"] == "scheduling_complete"
    assert result["stage"] == "schedule_handoff"
    assert result["reason"] is None
    assert "confirmation" in result
    assert result["confirmation"]["vin"] == "VIN-1001"  # camry's known VIN in mock inventory


def test_complete_scheduling_calls_mock_crm_with_correct_args():
    explanation_result = {
        "explanation_text": "irrelevant for this test",
        "action_plan": {"action": "schedule_test_drive", "vehicle_mention": "civic", "requested_date": "2026-10-06", "requested_time": "10am"},
    }
    with patch("schedule_handoff.mock_dealer_crm.schedule_test_drive", wraps=None) as spy:
        spy.return_value = {"confirmation_id": "CONF-TEST", "vin": "VIN-1002"}
        complete_scheduling(explanation_result)
        assert spy.call_count == 1
        called_vehicle_record, called_date, called_time = spy.call_args[0]
        assert called_vehicle_record["vin"] == "VIN-1002"
        assert called_date == "2026-10-06"
        assert called_time == "10am"


def test_unknown_vehicle_mention_degrades_gracefully_not_a_halt():
    explanation_result = {
        "explanation_text": "irrelevant for this test",
        "action_plan": {"action": "schedule_test_drive", "vehicle_mention": "zephyr9000", "requested_date": None, "requested_time": None},
    }
    result = complete_scheduling(explanation_result)
    assert result["status"] == "scheduling_complete"  # not a halt — no failure mode is modeled here
    assert result["confirmation"]["vin"] == "UNKNOWN"


if __name__ == "__main__":
    test_complete_scheduling_returns_locked_status_shape()
    test_complete_scheduling_calls_mock_crm_with_correct_args()
    test_unknown_vehicle_mention_degrades_gracefully_not_a_halt()
    print("All test_schedule_handoff.py tests passed.")
