import unittest

from src.gate import AuthorizationGate


class TestAuthorizationGateContract(unittest.TestCase):
    """
    These tests verify the Gate's CONTRACT -- that it demands a real,
    callable decision function and strictly validates its return value.
    They deliberately do NOT test what should authorize a transaction,
    because this Gate ships with no default authorization criteria and
    this repository has no basis for asserting one. See gate.py.
    """

    def test_raises_typeerror_if_decision_fn_is_none(self):
        with self.assertRaises(TypeError):
            AuthorizationGate(decision_fn=None)

    def test_raises_typeerror_if_decision_fn_is_not_callable(self):
        with self.assertRaises(TypeError):
            AuthorizationGate(decision_fn="not_a_function")

    def test_raises_typeerror_if_decision_fn_is_a_plain_bool(self):
        # Guards against someone passing True/False directly instead of a
        # function that returns True/False -- an easy mistake to make.
        with self.assertRaises(TypeError):
            AuthorizationGate(decision_fn=True)

    def test_honors_true_decision(self):
        gate = AuthorizationGate(decision_fn=lambda ctx: True)
        self.assertTrue(gate.decide({"amount": 50.0}))

    def test_honors_false_decision(self):
        gate = AuthorizationGate(decision_fn=lambda ctx: False)
        self.assertFalse(gate.decide({"amount": 50.0}))

    def test_raises_valueerror_on_non_bool_truthy_return(self):
        gate = AuthorizationGate(decision_fn=lambda ctx: 1)
        with self.assertRaises(ValueError):
            gate.decide({"amount": 50.0})

    def test_raises_valueerror_on_non_bool_falsy_return(self):
        gate = AuthorizationGate(decision_fn=lambda ctx: 0)
        with self.assertRaises(ValueError):
            gate.decide({"amount": 50.0})

    def test_raises_valueerror_on_none_return(self):
        gate = AuthorizationGate(decision_fn=lambda ctx: None)
        with self.assertRaises(ValueError):
            gate.decide({"amount": 50.0})

    def test_raises_valueerror_on_string_return(self):
        gate = AuthorizationGate(decision_fn=lambda ctx: "yes")
        with self.assertRaises(ValueError):
            gate.decide({"amount": 50.0})

    def test_context_is_passed_through_to_decision_fn_unmodified(self):
        received = {}

        def capture(ctx):
            received.update(ctx)
            return True

        gate = AuthorizationGate(decision_fn=capture)
        original_context = {"agent_id": "agent-x", "amount": 12.34}
        gate.decide(original_context)
        self.assertEqual(received, original_context)


if __name__ == "__main__":
    unittest.main()
