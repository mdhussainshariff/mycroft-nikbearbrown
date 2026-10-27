import unittest
from datetime import date

from src.permissions import PermissionOutcome, check_permissions


class TestPermissions(unittest.TestCase):
    def test_within_configured_limit_passes(self):
        result = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="household_staples",
            amount=42.50,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.WITHIN_LIMITS)
        self.assertIsNone(result.reason)

    def test_amount_exceeding_configured_limit_escalates(self):
        result = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="household_staples",
            amount=210.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.OUTSIDE_LIMIT)
        self.assertEqual(result.reason, "outside_spending_limit")

    def test_amount_exactly_at_limit_passes(self):
        # Boundary check: the configured limit for household_staples is
        # 150.00. A transaction of exactly 150.00 must pass -- the check
        # uses a strict ">" comparison, not ">=", so the limit itself is
        # an allowed amount, not a rejected one.
        result = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="household_staples",
            amount=150.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.WITHIN_LIMITS)

    def test_date_outside_active_window_escalates_as_timeframe_not_limit(self):
        result = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="household_staples",
            amount=10.00,  # comfortably within the spending limit
            transaction_date=date(2027, 3, 1),  # after active_until
        )
        self.assertEqual(result.outcome, PermissionOutcome.OUTSIDE_TIMEFRAME)
        self.assertEqual(result.reason, "outside_timeframe")

    def test_unconfigured_category_is_its_own_distinct_outcome(self):
        result = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="footwear",  # never configured for this agent
            amount=10.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.UNCONFIGURED)
        self.assertEqual(result.reason, "unconfigured_category")

    def test_unconfigured_category_checked_before_any_limit_comparison(self):
        # Even an enormous amount, for an unconfigured category, must
        # come back UNCONFIGURED -- not OUTSIDE_LIMIT -- because there is
        # no limit to compare it against in the first place. This proves
        # the ordering (unconfigured-check first) actually does work,
        # rather than merely being asserted in the docstring.
        result = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="footwear",
            amount=1_000_000.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.UNCONFIGURED)

    def test_unconfigured_and_outside_limit_reasons_are_distinct(self):
        unconfigured = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="footwear",
            amount=10.00,
            transaction_date=date(2026, 6, 1),
        )
        outside_limit = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="household_staples",
            amount=210.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertNotEqual(unconfigured.reason, outside_limit.reason)

    def test_unknown_consumer_agent_pair_treated_as_fully_unconfigured(self):
        result = check_permissions(
            consumer_id="someone-else",
            agent_id="agent-concierge-01",
            category="household_staples",
            amount=10.00,
            transaction_date=date(2026, 6, 1),
        )
        self.assertEqual(result.outcome, PermissionOutcome.UNCONFIGURED)

    def test_timeframe_checked_before_limit_when_both_are_violated(self):
        # Found during a second review pass: a transaction can violate BOTH the
        # spending limit and the active timeframe at once, and nothing
        # previously proved which reason wins. The code checks timeframe
        # first (see permissions.py), so this must deterministically
        # return OUTSIDE_TIMEFRAME, never OUTSIDE_LIMIT, for a transaction
        # that fails both -- documented as a deliberate choice in
        # docs/DESIGN_DECISIONS.md, Decision 010, not an accident of
        # whichever check happened to be written first.
        result = check_permissions(
            consumer_id="devon-01",
            agent_id="agent-concierge-01",
            category="household_staples",
            amount=999.00,  # comfortably over the 150.00 limit
            transaction_date=date(2027, 3, 1),  # comfortably outside the window
        )
        self.assertEqual(result.outcome, PermissionOutcome.OUTSIDE_TIMEFRAME)
        self.assertEqual(result.reason, "outside_timeframe")


if __name__ == "__main__":
    unittest.main()
