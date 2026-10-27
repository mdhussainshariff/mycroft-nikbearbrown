import unittest
from datetime import date

from src.orchestrator import TransactionPipeline
from src.permissions import PermissionOutcome, check_permissions, normalise_category


class TestCategoryNormalisation(unittest.TestCase):
    """
    Third review pass (DD012; README "What building it surfaced", #12). The permission lookup was an
    exact string match on a category label the agent itself supplies, so a
    configured category written differently looked exactly like a category
    the consumer never configured. Reproduced before the fix: Devon's
    groceries, $70, dated after Devon's active window, ESCALATED as
    "household_staples" but COMPLETED through the Gate as
    "Household_Staples".

    These tests pin both halves of the fix's deliberate scope: spelling
    variants now resolve to the configured entry; a synonym still does not.
    """

    def setUp(self):
        self.gate_calls = []

        def approve_everything(ctx):
            self.gate_calls.append(ctx)
            return True

        # A gate that approves everything, so any transaction that wrongly
        # reaches it would visibly complete.
        self.pipeline = TransactionPipeline(gate_decision_fn=approve_everything)

    def _devon(self, category, amount, transaction_date):
        return self.pipeline.process_transaction(
            agent_id="agent-concierge-01",
            consumer_id="devon-01",
            category=category,
            merchant="greenleaf-grocery",
            amount=amount,
            transaction_date=transaction_date,
        )

    def test_spelling_variants_share_one_canonical_form(self):
        for variant in ["Household_Staples", "  household_staples ", "household staples",
                        "HOUSEHOLD-STAPLES", "household__staples", "Household - Staples"]:
            with self.subTest(variant=variant):
                self.assertEqual(normalise_category(variant), "household_staples")

    def test_a_synonym_is_not_a_spelling_variant(self):
        # Deliberately out of scope: mapping synonyms would mean inventing a
        # category taxonomy Mastercard has not disclosed.
        self.assertNotEqual(normalise_category("groceries"), "household_staples")

    def test_case_variant_hits_the_configured_timeframe(self):
        result = check_permissions(
            consumer_id="devon-01", agent_id="agent-concierge-01",
            category="Household_Staples", amount=70.00,
            transaction_date=date(2027, 3, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.OUTSIDE_TIMEFRAME)

    def test_whitespace_variant_hits_the_configured_limit(self):
        result = check_permissions(
            consumer_id="devon-01", agent_id="agent-concierge-01",
            category="household_staples ", amount=200.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.OUTSIDE_LIMIT)

    def test_hyphen_variant_within_limits_passes(self):
        result = check_permissions(
            consumer_id="devon-01", agent_id="agent-concierge-01",
            category="household-staples", amount=42.50,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.WITHIN_LIMITS)

    def test_synonym_is_still_unconfigured(self):
        # Pins the documented boundary rather than hiding it: "groceries" is
        # a label Devon never configured, so it goes to the Gate.
        result = check_permissions(
            consumer_id="devon-01", agent_id="agent-concierge-01",
            category="groceries", amount=70.00,
            transaction_date=date(2027, 3, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.UNCONFIGURED)

    def test_separator_only_category_is_malformed_not_unconfigured(self):
        for junk in ["-", "___", " - ", "_ -"]:
            with self.subTest(category=junk):
                result = self._devon(junk, 20.00, date(2026, 6, 1))
                self.assertEqual(result.status, "REJECTED")
                self.assertEqual(result.reason, "malformed_transaction_input")
        self.assertEqual(self.gate_calls, [])

    def test_the_finding_itself_now_escalates_without_reaching_the_gate(self):
        result = self._devon("Household_Staples", 70.00, date(2027, 3, 1))
        self.assertEqual(result.status, "ESCALATED")
        self.assertEqual(result.reason, "outside_timeframe")
        self.assertEqual(self.gate_calls, [])  # never routed to the Gate
        self.assertIsNone(result.intent_record)

    def test_variant_within_limits_records_the_canonical_category(self):
        result = self._devon("HOUSEHOLD STAPLES", 42.50, date(2026, 6, 1))
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.intent_record.category, "household_staples")
        self.assertEqual(result.intent_record.authorized_via, "within_configured_limits")

    def test_gate_sees_the_canonical_category(self):
        result = self._devon("FootWear ", 68.00, date(2026, 6, 1))
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(len(self.gate_calls), 1)
        self.assertEqual(self.gate_calls[0]["category"], "footwear")
        self.assertEqual(result.intent_record.category, "footwear")


if __name__ == "__main__":
    unittest.main()
