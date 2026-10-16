"""
WHAT THIS FILE DOES: Runs Intake -> Plan -> Validation Gate -> Explain ->
Schedule Handoff in strict, fail-fast sequence. The only module (besides
schedule_handoff.py) permitted to import mock_data, and the only module
that selectively injects scheduling_constraints (to plan.py only) and
policy_rules (to validation_gate.py only) — this selective injection is
what keeps Halt #2 and Halt #3 provably non-overlapping (see /v3,
mock_business_rules.py's card). Contains no business logic of its own.

CONFIRMED: Mirrors Capital One's own disclosed sequence — understand -> plan
-> validate -> explain -> CRM handoff (Capital One tech blog, Mar. 5, 2025)
— without adding steps beyond what's confirmed.
"""

import intake
import plan as plan_module
import explain as explain_module
import schedule_handoff
from validation_gate import ValidationGate
from mock_data import mock_business_rules


def run_pipeline(raw_request, decision_fn):
    """Runs the full pipeline for one customer request. decision_fn is
    passed through to ValidationGate's construction — see validation_gate.py
    for its required signature (receives check outcomes only)."""

    parsed_request = intake.parse_request(raw_request)
    if parsed_request.get("status") == "halted":
        return parsed_request

    scheduling_constraints = mock_business_rules.get_scheduling_constraints()
    action_plan = plan_module.build_plan(parsed_request, scheduling_constraints)
    if action_plan.get("status") == "halted":
        return action_plan

    policy_rules = mock_business_rules.get_policy_rules()
    gate = ValidationGate(decision_fn)
    gate_result = gate.validate(action_plan, policy_rules)
    if gate_result.get("status") == "halted":
        return gate_result

    explanation_result = explain_module.generate_explanation(gate_result["validated_plan"])

    return schedule_handoff.complete_scheduling(explanation_result)
