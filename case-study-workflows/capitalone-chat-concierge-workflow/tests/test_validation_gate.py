"""
WHAT THIS FILE DOES: Unit tests for validation_gate.py. Covers: construction
without a decision function raises TypeError; an unrecognized decision
function return value raises ValueError (proving the gate cannot be
silently defeated by a malformed caller); the decision function receives
check outcomes ONLY, never the raw plan (locked per /review Pass 5); and the
full 2x2 hallucination-pass/fail x policy-pass/fail matrix.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validation_gate import ValidationGate

POLICY_RULES = {
    "max_advance_booking_days": 30,
    "restricted_vehicle_mentions": ["mustang"],
}

VALID_PLAN = {"action": "schedule_test_drive", "vehicle_mention": "camry"}
RESTRICTED_PLAN = {"action": "schedule_test_drive", "vehicle_mention": "mustang"}
MALFORMED_PLAN = {"action": "schedule_test_drive"}  # missing vehicle_mention


def test_construction_without_decision_fn_raises_type_error():
    try:
        ValidationGate(None)
        assert False, "expected TypeError"
    except TypeError:
        pass


def test_unrecognized_decision_value_raises_value_error():
    gate = ValidationGate(lambda h, p: "maybe")
    try:
        gate.validate(VALID_PLAN, POLICY_RULES)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_decision_fn_receives_check_outcomes_only_not_raw_plan():
    calls = []

    def spy_decision_fn(hallucination_result, policy_result):
        calls.append((hallucination_result, policy_result))
        return "validated"

    gate = ValidationGate(spy_decision_fn)
    gate.validate(VALID_PLAN, POLICY_RULES)

    assert len(calls) == 1
    hallucination_result, policy_result = calls[0]
    assert hallucination_result == {"passed": True, "detail": None}
    assert policy_result == {"passed": True, "detail": None}
    # Proves the raw plan was never passed: neither call arg is the plan dict itself.
    assert hallucination_result != VALID_PLAN
    assert policy_result != VALID_PLAN


def test_decision_fn_returning_not_validated_produces_halt():
    gate = ValidationGate(lambda h, p: "not_validated")
    result = gate.validate(VALID_PLAN, POLICY_RULES)
    assert result == {"status": "halted", "stage": "validation_gate", "reason": "not_validated"}


def test_decision_fn_returning_validated_produces_validated_plan():
    gate = ValidationGate(lambda h, p: "validated")
    result = gate.validate(VALID_PLAN, POLICY_RULES)
    assert result == {"validated_plan": VALID_PLAN}


def test_matrix_hallucination_pass_policy_pass():
    gate = ValidationGate(lambda h, p: "validated" if h["passed"] and p["passed"] else "not_validated")
    result = gate.validate(VALID_PLAN, POLICY_RULES)
    assert "validated_plan" in result


def test_matrix_hallucination_pass_policy_fail():
    gate = ValidationGate(lambda h, p: "validated" if h["passed"] and p["passed"] else "not_validated")
    result = gate.validate(RESTRICTED_PLAN, POLICY_RULES)
    assert result["status"] == "halted"
    assert result["reason"] == "not_validated"


def test_matrix_hallucination_fail_policy_pass():
    gate = ValidationGate(lambda h, p: "validated" if h["passed"] and p["passed"] else "not_validated")
    result = gate.validate(MALFORMED_PLAN, POLICY_RULES)
    assert result["status"] == "halted"
    assert result["reason"] == "not_validated"


def test_matrix_hallucination_fail_policy_fail():
    malformed_and_restricted = {"action": "schedule_test_drive", "vehicle_mention": ""}
    gate = ValidationGate(lambda h, p: "validated" if h["passed"] and p["passed"] else "not_validated")
    result = gate.validate(malformed_and_restricted, POLICY_RULES)
    assert result["status"] == "halted"
    assert result["reason"] == "not_validated"


if __name__ == "__main__":
    test_construction_without_decision_fn_raises_type_error()
    test_unrecognized_decision_value_raises_value_error()
    test_decision_fn_receives_check_outcomes_only_not_raw_plan()
    test_decision_fn_returning_not_validated_produces_halt()
    test_decision_fn_returning_validated_produces_validated_plan()
    test_matrix_hallucination_pass_policy_pass()
    test_matrix_hallucination_pass_policy_fail()
    test_matrix_hallucination_fail_policy_pass()
    test_matrix_hallucination_fail_policy_fail()
    print("All test_validation_gate.py tests passed.")
