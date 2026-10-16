"""
WHAT THIS FILE DOES: Proves the orchestrator's fail-fast sequencing via
spy/mock assertions — that later stages are never called after an earlier
halt, not just that the final result looks halted. Also proves the happy
path resolves end-to-end, and that both validation_gate.py's exceptions
propagate correctly through the orchestrator's entry point.
"""

import sys
import os
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import orchestrator

ALWAYS_VALIDATED = lambda h, p: "validated"
ALWAYS_NOT_VALIDATED = lambda h, p: "not_validated"


def test_intake_halt_stops_pipeline_before_plan():
    with patch("orchestrator.plan_module.build_plan") as plan_spy:
        result = orchestrator.run_pipeline("what colors does the Camry come in?", ALWAYS_VALIDATED)
        assert result["status"] == "halted"
        assert result["stage"] == "intake"
        assert result["reason"] == "unparseable_request"
        plan_spy.assert_not_called()


def test_plan_halt_stops_pipeline_before_validation_gate():
    with patch("orchestrator.ValidationGate") as gate_spy:
        # 2026-12-25 is a locked blackout date
        result = orchestrator.run_pipeline(
            "I'd like to schedule a test drive for the Camry on 2026-12-25 at 2pm", ALWAYS_VALIDATED
        )
        assert result["status"] == "halted"
        assert result["stage"] == "plan"
        assert result["reason"] == "infeasible_against_business_rules"
        gate_spy.assert_not_called()


def test_validation_gate_halt_stops_pipeline_before_explain():
    with patch("orchestrator.explain_module.generate_explanation") as explain_spy:
        result = orchestrator.run_pipeline(
            "I'd like to schedule a test drive for the Mustang on 2026-10-05 at 2pm", ALWAYS_NOT_VALIDATED
        )
        assert result["status"] == "halted"
        assert result["stage"] == "validation_gate"
        assert result["reason"] == "not_validated"
        explain_spy.assert_not_called()


def test_missing_decision_fn_raises_type_error_and_schedule_handoff_never_called():
    with patch("orchestrator.schedule_handoff.complete_scheduling") as handoff_spy:
        try:
            orchestrator.run_pipeline(
                "I'd like to schedule a test drive for the Camry on 2026-10-05 at 2pm", None
            )
            assert False, "expected TypeError"
        except TypeError:
            pass
        handoff_spy.assert_not_called()


def test_bad_decision_value_raises_value_error_and_schedule_handoff_never_called():
    with patch("orchestrator.schedule_handoff.complete_scheduling") as handoff_spy:
        try:
            orchestrator.run_pipeline(
                "I'd like to schedule a test drive for the Camry on 2026-10-05 at 2pm",
                lambda h, p: "maybe",
            )
            assert False, "expected ValueError"
        except ValueError:
            pass
        handoff_spy.assert_not_called()


def test_happy_path_resolves_end_to_end():
    result = orchestrator.run_pipeline(
        "I'd like to schedule a test drive for the Camry on 2026-10-05 at 2pm", ALWAYS_VALIDATED
    )
    assert result["status"] == "scheduling_complete"
    assert result["stage"] == "schedule_handoff"
    assert "confirmation" in result
    assert result["confirmation"]["vin"] == "VIN-1001"


if __name__ == "__main__":
    test_intake_halt_stops_pipeline_before_plan()
    test_plan_halt_stops_pipeline_before_validation_gate()
    test_validation_gate_halt_stops_pipeline_before_explain()
    test_missing_decision_fn_raises_type_error_and_schedule_handoff_never_called()
    test_bad_decision_value_raises_value_error_and_schedule_handoff_never_called()
    test_happy_path_resolves_end_to_end()
    print("All test_orchestrator.py tests passed.")
