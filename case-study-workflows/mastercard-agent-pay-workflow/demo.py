"""
Demo script -- exercises the pipeline end to end with a few example
transactions.

The `example_gate_policy` function below is a trivial, hardcoded rule
("approve unconfigured categories under $75") used ONLY so this demo can
run and show every terminal state at least once. It is deliberately NOT
marked [DEV] the way this repository's other constructed values are (see
docs/DESIGN_DECISIONS.md, Decision 004): a [DEV] marker signals a
legitimate illustrative default worth tuning toward something real. This
policy has no relationship to any real Mastercard authorization criterion
at all -- Mastercard has not disclosed one -- and exists solely to make
the Gate callable. Do not read anything into the $75 figure; it was
chosen to be low enough that the demo can show both an approval and an
escalation from the same unconfigured category.
"""

from datetime import date

from src.orchestrator import TransactionPipeline


def example_gate_policy(context: dict) -> bool:
    """NOT a Mastercard-derived rule. See module docstring above."""
    return context["amount"] < 75.00


def run_demo():
    pipeline = TransactionPipeline(gate_decision_fn=example_gate_policy)

    scenarios = [
        dict(
            label="Devon's shoes: unconfigured category, under the demo's $75 cutoff",
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="footwear",
            merchant="trailhead-running-co",
            amount=68.00,
            transaction_date=date(2026, 9, 1),
        ),
        dict(
            label="Same shoes, priced above the demo's $75 cutoff -> escalates",
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="footwear",
            merchant="trailhead-running-co",
            amount=140.00,
            transaction_date=date(2026, 9, 1),
        ),
        dict(
            label="Groceries: configured category, within Devon's $150 limit",
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=42.50,
            transaction_date=date(2026, 9, 1),
        ),
        dict(
            label="Groceries: configured category, OVER Devon's $150 limit",
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=210.00,
            transaction_date=date(2026, 9, 1),
        ),
        dict(
            label="Same agent, verification currently failing",
            agent_id="agent-concierge-02",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.00,
            transaction_date=date(2026, 9, 1),
        ),
        dict(
            label="An agent the network has never seen",
            agent_id="agent-never-registered-at-all",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.00,
            transaction_date=date(2026, 9, 1),
        ),
        dict(
            label="Devon's agent, claimed as acting for a DIFFERENT real consumer",
            agent_id="agent-concierge-01",  # actually registered to devon-01
            consumer_id="morgan-02",         # a real, but different, consumer
            category="electronics",
            merchant="citywide-electronics",
            amount=50.00,
            transaction_date=date(2026, 9, 1),
        ),
    ]

    for scenario in scenarios:
        label = scenario.pop("label")
        result = pipeline.process_transaction(**scenario)
        print(f"\n{label}")
        print(f"  status = {result.status}, reason = {result.reason}")
        if result.intent_record is not None:
            print(f"  intent_record = {result.intent_record}")


if __name__ == "__main__":
    run_demo()
