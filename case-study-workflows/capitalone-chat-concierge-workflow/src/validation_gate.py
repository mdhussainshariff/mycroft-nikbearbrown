"""
WHAT THIS FILE DOES: Runs two internal checks on an action plan — a
hallucination/error check and a policy-conformance check against
policy_rules — then defers the accept/reject decision ENTIRELY to an
externally supplied decision function. Ships with zero built-in acceptance
criteria: no confidence threshold, no dollar amount, no approval default of
any kind. Raises at construction if no decision function is supplied.

This is the deliberately-absent-default component of this build, matching
the pattern used for Lemonade's Authorization Gate, HSBC's Human Review
Gate, and DBS's Human Review Gate before it.

CONFIRMED: Capital One's own blog states both checks as distinct functions —
"[c]heck for hallucinations or errors" and "[s]imulate the execution of the
action plan and determine if the outcome conforms to policies and business
rules" (Capital One tech blog, Mar. 5, 2025).

CONSTRUCTED / DELIBERATELY ABSENT: The zero-default design is grounded
directly in Milind Naphade's own governance framing (VentureBeat, Jul. 2025):
AI capability innovation currently outpaces governance and control roughly
five to one — "we need to close this gap before we allow autonomy." No
source discloses what should happen when a plan is rejected, so this gate
does not invent an answer; it requires the caller to supply one.

Naming departure (logged in docs/DESIGN_DECISIONS.md): this gate's outcome
values are `validated` / `not_validated`, not this series' usual
`not_authorized` default — grounded directly in Capital One's own verb,
"validate that plan."
"""


class ValidationGate:
    def __init__(self, decision_fn):
        if decision_fn is None:
            raise TypeError(
                "ValidationGate requires a decision_fn at construction — "
                "no default acceptance criteria exist or ever will. "
                "See docs/DESIGN_DECISIONS.md for why."
            )
        self._decision_fn = decision_fn

    def validate(self, action_plan, policy_rules):
        """Runs both internal checks, then calls the caller-supplied
        decision_fn with the two check outcomes ONLY — never the raw
        action_plan (locked per /review Pass 5: this keeps the decision
        function a genuine contract boundary, not a place where plan
        content could be weighed over the check results)."""
        hallucination_check_result = self._check_hallucination(action_plan)
        policy_conformance_result = self._check_policy_conformance(action_plan, policy_rules)

        decision = self._decision_fn(hallucination_check_result, policy_conformance_result)

        if decision not in ("validated", "not_validated"):
            raise ValueError(
                f"decision_fn returned {decision!r}; must return "
                "'validated' or 'not_validated'. An unrecognized value is "
                "never treated as an implicit approval."
            )

        if decision == "not_validated":
            return {
                "status": "halted",
                "stage": "validation_gate",
                "reason": "not_validated",
            }

        return {"validated_plan": action_plan}

    def _check_hallucination(self, action_plan):
        """[DEV] CONSTRUCTED stand-in. A real hallucination check would
        compare the plan against actual retrieved data; this checks only
        for structural completeness of the plan object itself."""
        required_keys = {"action", "vehicle_mention"}
        if not required_keys.issubset(action_plan.keys()):
            return {"passed": False, "detail": "missing_required_fields"}
        if not action_plan.get("vehicle_mention"):
            return {"passed": False, "detail": "empty_vehicle_mention"}
        return {"passed": True, "detail": None}

    def _check_policy_conformance(self, action_plan, policy_rules):
        """[DEV] CONSTRUCTED stand-in. Checks the plan's vehicle mention
        against a fabricated restricted-vehicle list. Does not enforce
        max_advance_booking_days — documented limitation, not silently
        ignored (see docs/DESIGN_DECISIONS.md)."""
        restricted = policy_rules.get("restricted_vehicle_mentions", [])
        if action_plan.get("vehicle_mention") in restricted:
            return {"passed": False, "detail": "restricted_vehicle"}
        return {"passed": True, "detail": None}
