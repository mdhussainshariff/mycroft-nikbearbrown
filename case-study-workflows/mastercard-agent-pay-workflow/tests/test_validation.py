import unittest
from datetime import date, datetime

from src.validation import validate_transaction_input


class TestValidation(unittest.TestCase):
    """
    Regression tests for the three defects an adversarial pass found
    (Section 6 of the case study; docs/DESIGN_DECISIONS.md, Decision 007):
    a negative amount and a NaN amount both completing silently, and a
    string amount or string date crashing the pipeline outright.
    """

    VALID = dict(
        agent_id="agent-concierge-01",
        consumer_id="devon-01",
        category="household_staples",
        merchant="greenleaf-grocery",
        amount=42.50,
        transaction_date=date(2026, 6, 1),
    )

    def test_well_formed_input_passes(self):
        self.assertIsNone(validate_transaction_input(**self.VALID))

    def test_zero_amount_is_valid_not_malformed(self):
        # A $0 transaction is a legitimate edge case, not malformed input --
        # this must NOT be flagged, unlike a negative amount.
        kwargs = {**self.VALID, "amount": 0.0}
        self.assertIsNone(validate_transaction_input(**kwargs))

    def test_negative_amount_is_rejected(self):
        kwargs = {**self.VALID, "amount": -50.00}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_nan_amount_is_rejected(self):
        # This is the more serious of the three original findings: without
        # this check, NaN silently passed every downstream comparison and
        # the transaction completed as if it had been properly checked.
        kwargs = {**self.VALID, "amount": float("nan")}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_infinite_amount_is_rejected(self):
        kwargs = {**self.VALID, "amount": float("inf")}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_negative_infinite_amount_is_rejected(self):
        kwargs = {**self.VALID, "amount": float("-inf")}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_string_amount_is_rejected_not_crashed(self):
        kwargs = {**self.VALID, "amount": "42.50"}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_bool_amount_is_rejected(self):
        # bool is a subclass of int in Python; True/False must not silently
        # pass as 1/0.
        kwargs = {**self.VALID, "amount": True}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_none_amount_is_rejected(self):
        kwargs = {**self.VALID, "amount": None}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_string_date_gets_its_own_distinct_reason(self):
        kwargs = {**self.VALID, "transaction_date": "2026-06-01"}
        self.assertEqual(
            validate_transaction_input(**kwargs), "invalid_transaction_date"
        )

    def test_datetime_object_is_rejected_not_silently_accepted(self):
        # datetime.datetime is a SUBCLASS of datetime.date in Python, so
        # isinstance(x, date) alone is not enough -- a real datetime.datetime
        # object would otherwise pass that check and then crash downstream
        # in permissions.py, which cannot compare a plain date to a
        # datetime with <=. Found during a second review pass, after the original
        # adversarial pass had already closed the string-date crash but
        # missed this one.
        kwargs = {**self.VALID, "transaction_date": datetime(2026, 6, 1, 14, 30)}
        self.assertEqual(
            validate_transaction_input(**kwargs), "invalid_transaction_date"
        )

    def test_whitespace_only_agent_id_is_rejected(self):
        # Found during a second review pass: a bare `value == ""` check let a
        # whitespace-only string through, since "   " != "".
        kwargs = {**self.VALID, "agent_id": "   "}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_whitespace_only_category_is_rejected(self):
        kwargs = {**self.VALID, "category": "\t\n"}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_none_date_gets_the_date_specific_reason(self):
        kwargs = {**self.VALID, "transaction_date": None}
        self.assertEqual(
            validate_transaction_input(**kwargs), "invalid_transaction_date"
        )

    def test_none_category_is_malformed_not_unconfigured(self):
        # A missing category is a different claim from "a real category
        # the consumer never configured" -- it must be caught here, before
        # permissions.py ever gets a chance to treat it as UNCONFIGURED.
        kwargs = {**self.VALID, "category": None}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_empty_string_agent_id_is_rejected(self):
        kwargs = {**self.VALID, "agent_id": ""}
        self.assertEqual(
            validate_transaction_input(**kwargs), "malformed_transaction_input"
        )

    def test_malformed_input_reason_and_date_reason_are_distinct_strings(self):
        malformed = validate_transaction_input(**{**self.VALID, "amount": "bad"})
        bad_date = validate_transaction_input(
            **{**self.VALID, "transaction_date": "bad"}
        )
        self.assertNotEqual(malformed, bad_date)


if __name__ == "__main__":
    unittest.main()
