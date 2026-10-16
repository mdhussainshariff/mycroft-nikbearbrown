import unittest

from src.registration import check_registration


class TestRegistration(unittest.TestCase):
    def test_registered_and_verified_agent_passes(self):
        result = check_registration("agent-concierge-01")
        self.assertTrue(result.registered)
        self.assertTrue(result.verified)
        self.assertIsNone(result.reason)
        self.assertEqual(result.consumer_id, "devon-01")

    def test_registered_but_unverified_agent_fails_with_distinct_reason(self):
        result = check_registration("agent-concierge-02")
        self.assertTrue(result.registered)
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "unverified_agent")

    def test_unknown_agent_id_fails_as_unregistered(self):
        result = check_registration("agent-never-seen-before")
        self.assertFalse(result.registered)
        self.assertEqual(result.reason, "unregistered_agent")

    def test_unregistered_and_unverified_reasons_are_distinct_strings(self):
        # Regression guard: these two failure reasons must never collapse
        # into the same string, since Section 4 of the case study treats
        # them as two separate preconditions, not one.
        unregistered = check_registration("agent-never-seen-before")
        unverified = check_registration("agent-concierge-02")
        self.assertNotEqual(unregistered.reason, unverified.reason)


if __name__ == "__main__":
    unittest.main()
