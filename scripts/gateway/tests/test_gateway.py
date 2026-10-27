import pytest

from gateway.adapters.fake import FakeAdapter
from gateway.client import GatewayClient
from gateway.gateway import Gateway
from gateway.logbook import Logbook
from gateway.policy import Policy
from gateway.tiers import TierConfig

LABELS = ["positive", "negative", "neutral"]


def build(log_path, prices, *, start="cheap", escalate="mid", cheap_budget=512):
    """A gateway on fake adapters, priced by the conftest fixture table.

    `escalate=None` means this task type is never retried.
    """
    tiers = TierConfig({"version": "t", "tiers": {
        "cheap": {"provider": "groq", "model": "small", "status": "evidenced",
                  "evidence": "test", "context_limit": 131072, "capabilities": ["text"]},
        "mid": {"provider": "groq", "model": "large", "status": "evidenced",
                "evidence": "test", "context_limit": 131072, "capabilities": ["text"]},
        "strong": {"provider": "anthropic", "model": "strong", "status": "evidenced",
                   "evidence": "test", "context_limit": 131072, "capabilities": ["text"]},
    }})
    policy = Policy({
        "version": "p",
        "tier_order": ["cheap", "mid", "strong"],
        "max_tokens_by_tier": {"cheap": cheap_budget, "mid": 512, "strong": 1024},
        "task_types": {"sentiment_classification": {
            "description": "Label the text.", "output": "label", "labels": LABELS,
            "validator": "label_in_set", "quality_check": "deterministic",
            "start_tier": start, "escalate_to": escalate,
            "promote_above_chars": 100000, "evidence": ["x"]}}}, tiers)

    groq, anthropic = FakeAdapter(provider="groq"), FakeAdapter(provider="anthropic")
    client = GatewayClient(logbook=Logbook(log_path, prices),
                           adapters={"groq": groq, "anthropic": anthropic},
                           tiers=tiers.as_client_map(), policy_version="p",
                           clock=lambda: 0.0)
    gateway = Gateway(client=client, policy=policy, tiers=tiers, caller="test")
    return gateway, groq, anthropic


def ask(gateway):
    return gateway.handle(task_type="sentiment_classification",
                          text="Fake Industries beat estimates.")


def test_a_good_answer_is_not_retried(log_path, prices_v1):
    gateway, groq, _ = build(log_path, prices_v1)
    groq.queue_response("positive")

    result = ask(gateway)

    assert result.passed and result.text == "positive"
    assert (result.attempts, result.escalated) == (1, False)
    assert len(groq.calls) == 1


def test_a_failed_check_escalates_exactly_once(log_path, prices_v1):
    gateway, groq, _ = build(log_path, prices_v1)
    groq.queue_response("bullish").queue_response("positive")

    result = ask(gateway)

    assert result.passed and result.escalated
    assert [r["tier"] for r in result.records] == ["cheap", "mid"]
    assert [r["attempt_no"] for r in result.records] == [1, 2]
    assert [r["routing_reason"] for r in result.records] == ["policy", "escalation"]
    assert [r["outcome"] for r in result.records] == ["validator_fail", "ok"]
    assert len({r["request_id"] for r in result.records}) == 1


def test_two_failures_never_produce_a_third_attempt(log_path, prices_v1):
    gateway, groq, _ = build(log_path, prices_v1)
    groq.queue_response("bullish").queue_response("bearish")

    result = ask(gateway)

    assert not result.passed
    assert result.attempts == 2, "one retry only, never a chain"
    assert len(groq.calls) == 2


def test_a_terminal_provider_error_is_never_retried(log_path, prices_v1):
    """Every tier shares one key, so a 401 fails identically on the next one."""
    gateway, groq, _ = build(log_path, prices_v1)
    groq.queue_error(message="AuthenticationError: 401", retryable=False)

    result = ask(gateway)

    assert not result.passed and "401" in result.error
    assert result.attempts == 1
    assert len(groq.calls) == 1


def test_a_transient_provider_error_is_retried_once(log_path, prices_v1):
    gateway, groq, _ = build(log_path, prices_v1)
    groq.queue_error(kind="timeout", message="deadline exceeded").queue_response("positive")

    result = ask(gateway)

    assert result.passed
    assert [r["outcome"] for r in result.records] == ["timeout", "ok"]


def test_a_task_type_with_no_escalation_is_never_retried(log_path, prices_v1):
    """escalate_to null is how a top-tier task says 'there is nowhere to go'."""
    gateway, _, anthropic = build(log_path, prices_v1, start="strong", escalate=None)
    anthropic.queue_response("bullish")

    result = ask(gateway)

    assert not result.passed
    assert result.attempts == 1
    assert len(anthropic.calls) == 1


def test_truncation_triggers_the_retry(log_path, prices_v1):
    """tokens_out hitting the budget is a free, deterministic failure signal.

    The fake adapter counts tokens as words, so a two-word answer fills a
    two-token budget exactly.
    """
    gateway, groq, _ = build(log_path, prices_v1, cheap_budget=2)
    groq.queue_response("positive positive").queue_response("positive")

    result = ask(gateway)

    assert result.records[0]["validator_result"]["reason"] == "truncated"
    assert result.escalated and result.passed


def test_cost_and_latency_roll_up_across_both_attempts(log_path, prices_v1):
    gateway, groq, _ = build(log_path, prices_v1)
    groq.queue_response("bullish").queue_response("positive")

    result = ask(gateway)

    assert result.total_cost_usd == pytest.approx(
        sum(r["cost_usd"] for r in result.records))
    assert result.attempts == 2 and result.total_cost_usd > 0


def test_the_routing_explanation_is_recorded_on_the_first_attempt(log_path, prices_v1):
    gateway, groq, _ = build(log_path, prices_v1)
    groq.queue_response("positive")

    result = ask(gateway)

    assert "starts on cheap by policy" in result.records[0]["notes"]


def test_the_retry_records_why_it_happened(log_path, prices_v1):
    gateway, groq, _ = build(log_path, prices_v1)
    groq.queue_response("bullish").queue_response("positive")

    result = ask(gateway)

    assert "retry after check failed" in result.records[1]["notes"]
    assert "label_not_in_set" in result.records[1]["notes"]


def test_the_retry_uses_the_escalation_tiers_budget(log_path, prices_v1):
    gateway, groq, _ = build(log_path, prices_v1, cheap_budget=2)
    groq.queue_response("positive positive").queue_response("positive")

    ask(gateway)

    assert [c["max_tokens"] for c in groq.calls] == [2, 512]