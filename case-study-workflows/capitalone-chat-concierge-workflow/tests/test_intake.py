"""
WHAT THIS FILE DOES: Unit tests for intake.py — proves the completeness
check (test-drive intent + recognizable vehicle mention) fires correctly,
and that halt output matches the shared status-object contract.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from intake import parse_request


def test_valid_request_parses_successfully():
    result = parse_request("I'd like to schedule a test drive for the Camry on 2026-10-05 at 2pm")
    assert "status" not in result
    assert result["vehicle_mention"] == "camry"
    assert result["requested_date"] == "2026-10-05"
    assert result["requested_time"].lower().replace(" ", "") == "2pm"


def test_missing_test_drive_intent_halts():
    result = parse_request("What colors does the Camry come in?")
    assert result["status"] == "halted"
    assert result["stage"] == "intake"
    assert result["reason"] == "unparseable_request"


def test_missing_vehicle_mention_halts():
    result = parse_request("I want to schedule a test drive please")
    assert result["status"] == "halted"
    assert result["reason"] == "unparseable_request"


def test_empty_string_halts():
    result = parse_request("")
    assert result["status"] == "halted"
    assert result["reason"] == "unparseable_request"


def test_none_input_halts():
    result = parse_request(None)
    assert result["status"] == "halted"
    assert result["reason"] == "unparseable_request"


def test_request_without_date_or_time_still_parses():
    result = parse_request("Can I test drive the Civic?")
    assert "status" not in result
    assert result["vehicle_mention"] == "civic"
    assert result["requested_date"] is None
    assert result["requested_time"] is None


if __name__ == "__main__":
    test_valid_request_parses_successfully()
    test_missing_test_drive_intent_halts()
    test_missing_vehicle_mention_halts()
    test_empty_string_halts()
    test_none_input_halts()
    test_request_without_date_or_time_still_parses()
    print("All test_intake.py tests passed.")
