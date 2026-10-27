import unittest
from datetime import date
from unittest.mock import patch

from src.orchestrator import TransactionPipeline


class TestOrchestratorFailFast(unittest.TestCase):
    """
    These tests use mock/spy assertions to prove sequencing directly --
    confirming not just that a transaction is rejected or escalated with
    the right reason, but that LATER stages were never called at all.
    That is the actual proof of the fail-fast guarantee, not an
    assumption resting on the design description alone (the same
    discipline this series applied at CommBank, Lemonade, and Zurich).
    """

    def setUp(self):
        self.pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: True)

    def test_construction_fails_immediately_without_a_decision_fn(self):
        # The Gate is built at TransactionPipeline construction time, not
        # lazily on first use -- so a pipeline built with no real
        # authorization policy fails at construction, before it has
        # processed a single transaction.
        with self.assertRaises(TypeError):
            TransactionPipeline(gate_decision_fn=None)

    @patch("src.orchestrator.registration.check_registration")
    def test_malformed_input_never_reaches_registration_check(self, mock_check_registration):
        # Added after the adversarial pass: input validation must run
        # BEFORE registration, not just before permissions -- a NaN
        # amount or a negative amount should never even reach a lookup
        # against the registered-agent directory.
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
        mock_check_registration.assert_not_called()

    @patch("src.orchestrator.registration.check_registration")
    def test_invalid_date_never_reaches_registration_check(self, mock_check_registration):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.0,
            transaction_date="2026-06-01",  # string, not a date
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "invalid_transaction_date")
        mock_check_registration.assert_not_called()

    @patch("src.orchestrator.permissions.check_permissions")
    def test_unregistered_agent_never_reaches_permission_check(self, mock_check_permissions):
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
        mock_check_permissions.assert_not_called()

    @patch("src.orchestrator.permissions.check_permissions")
    def test_agent_consumer_mismatch_never_reaches_permission_check(self, mock_check_permissions):
        # The core proof for the CRITICAL finding: registration succeeding
        # is not enough on its own -- a mismatch between the agent's real
        # owner and the claimed consumer_id must stop the pipeline before
        # permissions.py (and therefore the Gate) ever runs, not merely
        # fall through to an ordinary "unconfigured" outcome.
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="morgan-02",
            category="electronics",
            merchant="citywide-electronics",
            amount=50.0,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "agent_consumer_mismatch")
        mock_check_permissions.assert_not_called()

    @patch("src.orchestrator.create_intent_record")
    def test_agent_consumer_mismatch_never_reaches_intent_record_creation(self, mock_create_intent_record):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="morgan-02",
            category="electronics",
            merchant="citywide-electronics",
            amount=50.0,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        mock_create_intent_record.assert_not_called()

    def test_correct_owner_is_not_flagged_as_a_mismatch(self):
        # Regression guard in the opposite direction: fixing #1 must not
        # start rejecting the agent's own, correct owner.
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",  # the agent's actual registered owner
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=42.50,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "COMPLETED")

    @patch("src.orchestrator.create_intent_record")
    def test_unverified_agent_never_reaches_intent_record_creation(self, mock_create_intent_record):
        result = self.pipeline.process_transaction(
            agent_id="agent-concierge-02",  # registered, verification failing
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.0,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "REJECTED")
        mock_create_intent_record.assert_not_called()

    def test_gate_is_never_invoked_for_outside_limit_transactions(self):
        gate_calls = []

        def spy_decision_fn(ctx):
            gate_calls.append(ctx)
            return True

        pipeline = TransactionPipeline(gate_decision_fn=spy_decision_fn)
        result = pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",  # configured category
            merchant="greenleaf-grocery",
            amount=210.00,  # exceeds the configured 150.00 limit
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.status, "ESCALATED")
        self.assertEqual(result.reason, "outside_spending_limit")
        self.assertEqual(
            len(gate_calls), 0,
            "The Gate must not be called for an unambiguous limit violation.",
        )

    def test_gate_is_never_invoked_for_outside_timeframe_transactions(self):
        gate_calls = []

        def spy_decision_fn(ctx):
            gate_calls.append(ctx)
            return True

        pipeline = TransactionPipeline(gate_decision_fn=spy_decision_fn)
        result = pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="household_staples",
            merchant="greenleaf-grocery",
            amount=10.00,
            transaction_date=date(2027, 3, 1),  # outside active window
        )
        self.assertEqual(result.status, "ESCALATED")
        self.assertEqual(result.reason, "outside_timeframe")
        self.assertEqual(len(gate_calls), 0)

    def test_gate_is_invoked_exactly_once_for_unconfigured_category(self):
        gate_calls = []

        def spy_decision_fn(ctx):
            gate_calls.append(ctx)
            return True

        pipeline = TransactionPipeline(gate_decision_fn=spy_decision_fn)
        pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="footwear",  # unconfigured
            merchant="trailhead-running-co",
            amount=68.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(len(gate_calls), 1)

    def test_gate_rejection_never_reaches_intent_record_creation(self):
        pipeline = TransactionPipeline(gate_decision_fn=lambda ctx: False)
        with patch("src.orchestrator.create_intent_record") as mock_create:
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
            mock_create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
