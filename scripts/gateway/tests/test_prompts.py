import pytest

from gateway.policy import Policy
from gateway.prompts import build
from gateway.tiers import TierConfig


@pytest.fixture
def policy():
    return Policy.load(TierConfig.load())


def rule_for(policy, task_type):
    return policy.rule_for(task_type)


def test_every_task_type_builds_a_prompt_stating_its_task(policy):
    extras = {
        "structured_extraction": {"required_keys": ["metric", "direction", "period"]},
        "rag_answer": {"context": ["passage one", "passage two"]},
    }
    for task_type in policy.task_types:
        rule = rule_for(policy, task_type)
        prompt = build(rule, "some input", **extras.get(task_type, {}))
        assert rule["description"] in prompt, task_type
        assert "some input" in prompt, task_type


def test_a_label_prompt_lists_every_allowed_label(policy):
    rule = rule_for(policy, "sentiment_classification")
    prompt = build(rule, "Fake Industries beat estimates.")
    for label in rule["labels"]:
        assert label in prompt
    assert "One word only" in prompt


def test_the_topic_prompt_carries_all_six_topics(policy):
    rule = rule_for(policy, "topic_classification")
    prompt = build(rule, "headline")
    assert all(label in prompt for label in rule["labels"])


def test_extraction_names_the_keys_and_forbids_null(policy):
    """required_keys treats null as missing, so 'none' is the honest answer."""
    rule = rule_for(policy, "structured_extraction")
    prompt = build(rule, "CFO said revenue will rise.",
                   required_keys=["metric", "direction", "period"])
    assert "metric, direction, period" in prompt
    assert '"none"' in prompt and "Never use null" in prompt


def test_extraction_without_keys_refuses_to_build(policy):
    with pytest.raises(ValueError, match="required_keys"):
        build(rule_for(policy, "structured_extraction"), "text")


def test_the_verdict_prompt_demands_json_and_a_copied_quote(policy):
    rule = rule_for(policy, "contradiction_detection")
    prompt = build(rule, "Statement A ... Statement B ...")
    assert "single JSON object" in prompt
    assert "word for word" in prompt
    assert "insufficient_evidence" in prompt


def test_the_summary_prompt_forbids_converting_units(policy):
    """numbers_grounded rejects any number absent from the input."""
    prompt = build(rule_for(policy, "summarization"), "margin expanded 150 basis points")
    assert "Do not convert units" in prompt
    assert "copied exactly" in prompt


def test_the_rag_prompt_numbers_the_passages_and_asks_for_a_citation(policy):
    rule = rule_for(policy, "rag_answer")
    prompt = build(rule, "What is a dividend?",
                   context=["Dividends come from profits.", "Bonds pay coupons."])
    assert "[0] Dividends come from profits." in prompt
    assert "[1] Bonds pay coupons." in prompt
    assert "Cite the passage" in prompt


def test_rag_without_passages_refuses_to_build(policy):
    with pytest.raises(ValueError, match="context"):
        build(rule_for(policy, "rag_answer"), "What is a dividend?")


def test_prompts_are_deterministic(policy):
    rule = rule_for(policy, "sentiment_classification")
    assert build(rule, "same text") == build(rule, "same text")