import unittest
from datetime import date

from src.intent_record import create_intent_record


class TestIntentRecord(unittest.TestCase):
    def test_record_captures_all_transaction_fields(self):
        record = create_intent_record(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category="footwear",
            merchant="trailhead-running-co",
            amount=68.00,
            transaction_date=date(2026, 9, 1),
            authorized_via="authorization_gate",
        )
        self.assertEqual(record.agent_id, "agent-concierge-01")
        self.assertEqual(record.consumer_id, "devon-01")
        self.assertEqual(record.category, "footwear")
        self.assertEqual(record.merchant, "trailhead-running-co")
        self.assertEqual(record.amount, 68.00)
        self.assertEqual(record.transaction_date, date(2026, 9, 1))
        self.assertEqual(record.authorized_via, "authorization_gate")

    def test_authorized_via_distinguishes_limit_path_from_gate_path(self):
        via_limits = create_intent_record(
            agent_id="a",
            consumer_id="c",
            category="household_staples",
            merchant="m",
            amount=10.0,
            transaction_date=date(2026, 1, 1),
            authorized_via="within_configured_limits",
        )
        via_gate = create_intent_record(
            agent_id="a",
            consumer_id="c",
            category="footwear",
            merchant="m",
            amount=10.0,
            transaction_date=date(2026, 1, 1),
            authorized_via="authorization_gate",
        )
        self.assertNotEqual(via_limits.authorized_via, via_gate.authorized_via)

    def test_record_has_a_created_at_timestamp(self):
        record = create_intent_record(
            agent_id="a",
            consumer_id="c",
            category="household_staples",
            merchant="m",
            amount=10.0,
            transaction_date=date(2026, 1, 1),
            authorized_via="within_configured_limits",
        )
        self.assertIsNotNone(record.created_at)


if __name__ == "__main__":
    unittest.main()
