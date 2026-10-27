"""
WHAT THIS FILE DOES: Provides two independent, fabricated rule sets used by
different pipeline stages — scheduling_constraints (consumed only by plan.py)
and policy_rules (consumed only by validation_gate.py). Neither stage receives
the other's section. This split exists specifically so Plan's feasibility
check and Validation Gate's policy-conformance check cannot silently overlap
(see /review Pass 5, capital-one-v3-component-cards.md).

CONSTRUCTED IN FULL. Capital One's own disclosure confirms that a
policy-conformance check happens (its blog: "simulate the execution of the
action plan and determine if the outcome conforms to policies and business
rules") — it discloses none of the policies themselves, and nothing at all
about scheduling constraints. Every value below is fabricated for testability.

[DEV]: Every value in SCHEDULING_CONSTRAINTS and POLICY_RULES is a placeholder.
Replace with whatever rule shape actually fits your use case if adapting this
reference implementation.
"""

import copy

# [DEV] Fabricated dealership scheduling constraints. Consumed only by plan.py.
SCHEDULING_CONSTRAINTS = {
    "operating_days": [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    ],  # [DEV] Closed Sundays — invented, not Capital One-confirmed.
    "operating_hours": {"open": "09:00", "close": "18:00"},  # [DEV] invented
    "blackout_dates": ["2026-12-25", "2026-01-01"],  # [DEV] invented holidays
}

# [DEV] Fabricated policy/business-rule conformance criteria. Consumed only
# by validation_gate.py's internal policy-conformance check.
POLICY_RULES = {
    "max_advance_booking_days": 30,  # [DEV] invented, not currently enforced by a check (documented limitation)
    "restricted_vehicle_mentions": ["mustang"],  # [DEV] invented — stand-in for vehicles requiring manual review before autonomous scheduling
}


def get_scheduling_constraints():
    """Returns a fresh copy of SCHEDULING_CONSTRAINTS so callers can't
    mutate the shared fixture across test cases."""
    return copy.deepcopy(SCHEDULING_CONSTRAINTS)


def get_policy_rules():
    """Returns a fresh copy of POLICY_RULES so callers can't mutate the
    shared fixture across test cases."""
    return copy.deepcopy(POLICY_RULES)
