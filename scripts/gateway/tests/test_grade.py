import pytest

from gateway.bench.run import grade
from gateway.gateway import GatewayResult
from gateway.router import RoutingDecision

DECISION = RoutingDecision(task_type="t", tier="cheap", escalate_to="mid",
                           max_tokens=512, routing_reason="policy",
                           explanation="x", policy_version="p")


def result_with(validator_result, passed=True):
    record = {"tier": "cheap", "outcome": "ok" if passed else "validator_fail",
              "validator_result": validator_result, "cost_usd": 0.0, "latency_ms": 1}
    return GatewayResult(request_id="r", task_type="t", decision=DECISION,
                         records=[record], text="answer", passed=passed)


def test_a_correct_label_is_graded_correct():
    fixture = {"expected": {"label": "positive"}}
    assert grade(fixture, result_with({"passed": True, "label": "positive"}))["correct"]


def test_a_wrong_label_that_passed_the_check_is_the_number_this_run_exists_for():
    """Allowed label, wrong answer: no free check can catch it."""
    fixture = {"expected": {"label": "positive"}}
    scored = grade(fixture, result_with({"passed": True, "label": "negative"}))

    assert scored["graded"] and scored["correct"] is False
    assert (scored["expected"], scored["got"]) == ("positive", "negative")


def test_a_verdict_is_graded_like_a_label():
    fixture = {"expected": {"label": "contradiction"}}
    assert grade(fixture, result_with({"passed": True,
                                       "verdict": "contradiction"}))["correct"]


def test_citing_the_right_passage_is_correct():
    fixture = {"expected": {"cite": 1}}
    assert grade(fixture, result_with({"passed": True, "cited": [1]}))["correct"]


def test_citing_the_wrong_passage_is_incorrect():
    fixture = {"expected": {"cite": 1}}
    assert grade(fixture, result_with({"passed": True, "cited": [0]}))["correct"] is False


def test_an_answer_that_failed_every_attempt_grades_as_wrong_not_missing():
    fixture = {"expected": {"label": "positive"}}
    scored = grade(fixture, result_with({"passed": False, "reason": "label_not_in_set"},
                                        passed=False))
    assert scored["graded"] and scored["correct"] is False and scored["got"] is None


def test_extraction_is_not_graded_because_the_check_cannot_judge_it():
    fixture = {"expected": {"required_keys": ["metric"]}}
    scored = grade(fixture, result_with({"passed": True, "keys": ["metric"]}))
    assert scored["graded"] is False and "invented" in scored["reason"]


def test_open_prose_is_not_graded_until_the_judge_exists():
    fixture = {"expected": {}}
    scored = grade(fixture, result_with({"passed": True}))
    assert scored["graded"] is False and "Sprint 5" in scored["reason"]