import unittest
from datetime import date

from src.orchestrator import TransactionPipeline


class TestEscalationReasons(unittest.TestCase):
    """
    Confirms all seven named terminal outcomes are each independently
    reachable with the correct status and reason attached -- two REJECTED
    reasons, three ESCALATED reasons, one Gate-driven ESCALATED reason,
    and COMPLETED (covered in test_happy_path.py).
    """

    def setUp(self):
        self.pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: True)

    def test_malformed_transaction_input(self):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=float("nan"),
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "malformed_transaction_input")

    def test_invalid_transaction_date(self):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.0,
            transaction_date="2026-06-01",
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "invalid_transaction_date")

    def test_unregistered_agent(self):
        result = self.pipeline.process_transaction(
            agent_id="agent-never-seen-before",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.0,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "unregistered_agent")

    def test_registered_but_unverified_agent(self):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-02",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.0,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "unverified_agent")

    def test_agent_consumer_mismatch(self):
        # agent-concierge-01 is genuinely registered and verified -- just
        # not for the consumer this call claims it's acting for. This is
        # the CRITICAL finding from the second review: before this fix,
        # this call completed successfully.
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",   # actually registered to devon-01
            consumer_id="morgan-02",          # a real, different consumer
            category="electronics",
            merchant="citywide-electronics",
            amount=50.0,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "agent_consumer_mismatch")

    def test_outside_spending_limit(self):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=210.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "ESCALATED")
        self.assertEqual(result.reason, "outside_spending_limit")

    def test_outside_timeframe(self):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.00,
            transaction_date=date(2027, 3, 1),
        )
        self.assertEqual(result.status, "ESCALATED")
        self.assertEqual(result.reason, "outside_timeframe")

    def test_not_authorized_by_gate(self):
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
        self.assertEqual(result.reason, "not_authorized_by_gate")

    def test_completed_within_limits(self):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=42.50,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertIsNone(result.reason)

    def test_completed_via_gate_approval(self):
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
        self.assertEqual(result.intent_record.authorized_via, "authorization_gate")

    def test_all_reject_and_escalate_reasons_are_pairwise_distinct(self):
        # Collect actual reason strings directly rather than re-deriving
        # them, so this test fails loudly if two paths ever converge on
        # the same string.
        results = [
            self.pipeline.process_transaction(
                agent_id="agent-concierge-01", consumer_id="devon-01",
                category="household_staples", merchant="greenleaf-grocery",
                amount=float("nan"), transaction_date=date(2026, 6, 1),
            ).reason,
            self.pipeline.process_transaction(
                agent_id="agent-concierge-01", consumer_id="devon-01",
                category="household_staples", merchant="greenleaf-grocery",
                amount=10.0, transaction_date="2026-06-01",
            ).reason,
            self.pipeline.process_transaction(
                agent_id="agent-never-seen-before", consumer_id="devon-01",
                category="household_staples", merchant="greenleaf-grocery",
                amount=10.0, transaction_date=date(2026, 6, 1),
            ).reason,
            self.pipeline.process_transaction(
                agent_id="agent-concierge-02", consumer_id="devon-01",
                category="household_staples", merchant="greenleaf-grocery",
                amount=10.0, transaction_date=date(2026, 6, 1),
            ).reason,
            self.pipeline.process_transaction(
                agent_id="agent-concierge-01", consumer_id="morgan-02",
                category="electronics", merchant="citywide-electronics",
                amount=50.0, transaction_date=date(2026, 6, 1),
            ).reason,
            self.pipeline.process_transaction(
                agent_id="agent-concierge-01", consumer_id="devon-01",
                category="household_staples", merchant="greenleaf-grocery",
                amount=210.0, transaction_date=date(2026, 6, 1),
            ).reason,
            self.pipeline.process_transaction(
                agent_id="agent-concierge-01", consumer_id="devon-01",
                category="household_staples", merchant="greenleaf-grocery",
                amount=10.0, transaction_date=date(2027, 3, 1),
            ).reason,
        ]
        self.assertEqual(len(results), len(set(results)), f"Reasons collided: {results}")


if __name__ == "__main__":
    unittest.main()
