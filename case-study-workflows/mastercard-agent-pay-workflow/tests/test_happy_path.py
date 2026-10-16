import unittest
from datetime import date

from src.orchestrator import TransactionPipeline


class TestHappyPath(unittest.TestCase):
    """
    The Devon/running-shoes scenario from Section 4 of the case study,
    run end to end -- proving the clean, fully-approved path works, not
    only the halt paths covered elsewhere.
    """

    def test_configured_category_within_limits_completes_and_records_intent(self):
        pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: True)
        result = pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=42.50,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertIsNotNone(result.intent_record)
        self.assertEqual(result.intent_record.authorized_via, "within_configured_limits")

    def test_unconfigured_category_approved_by_gate_completes_and_records_intent(self):
        pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: True)
        result = pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="footwear",
            merchant="trailhead-running-co",
            amount=68.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertIsNotNone(result.intent_record)
        self.assertEqual(result.intent_record.merchant, "trailhead-running-co")
        self.assertEqual(result.intent_record.authorized_via, "authorization_gate")

    def test_intent_record_is_never_created_for_a_rejected_transaction(self):
        pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: True)
        result = pipeline.process_transaction(
            agent_id="agent-unknown-99",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertIsNone(result.intent_record)

    def test_intent_record_is_never_created_for_an_escalated_transaction(self):
        pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: False)
        result = pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="footwear",
            merchant="trailhead-running-co",
            amount=68.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "ESCALATED")
        self.assertIsNone(result.intent_record)


    def test_second_consumers_own_agent_completes_normally(self):
        # Sanity check that the ownership fix doesn't break a genuinely
        # correct, different consumer/agent pairing.
        pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: True)
        result = pipeline.process_transaction(
            agent_id="agent-concierge-03",
            consumer_id="morgan-02",  # this agent's actual registered owner
            category="electronics",
            merchant="citywide-electronics",
            amount=120.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.intent_record.consumer_id, "morgan-02")

    def test_intent_record_is_never_created_for_an_ownership_mismatch(self):
        pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: True)
        result = pipeline.process_transaction(
            agent_id="agent-concierge-01",  # actually devon-01's agent
            consumer_id="morgan-02",         # claimed for a different consumer
            category="electronics",
            merchant="citywide-electronics",
            amount=50.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "agent_consumer_mismatch")
        self.assertIsNone(result.intent_record)


if __name__ == "__main__":
    unittest.main()
