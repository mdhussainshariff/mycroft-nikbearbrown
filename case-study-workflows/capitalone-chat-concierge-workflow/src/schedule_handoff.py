"""
WHAT THIS FILE DOES: Terminal pipeline stage. Receives an explained,
validated plan and writes the appointment to the mock dealer CRM. This is
the module added during /v2 to fill a gap the original blueprint's file
layout left open: CRM scheduling is a CONFIRMED capability (Case Study
Section 3.1) with no corresponding component in the blueprint as originally
drafted. It is isolated in its own thin stub — deliberately not folded into
explain.py — because writing to the CRM is a genuine side effect against
external (mock) state, unlike explain.py's pure-function text generation;
merging them would have made it impossible to prove via spy assertion that
scheduling only happens after explanation completes.

This is the one module, besides orchestrator.py, permitted to import
mock_data — a locked fetch-boundary exception (see /v2), granted because
this stage's entire job is a side-effecting action, not a computation.

CONFIRMED: test-drive scheduling integrates with the dealer's CRM system as
the terminal action for a validated plan (Case Study Section 3.1; Workflow
Summary table, Step 6, "Autonomous (confirmed integration)").

CONSTRUCTED: The internal mechanism is a stub — no real CRM protocol is
modeled. Named `scheduling_complete`, not `handoff_attempted` (the DBS
precedent's name) — this stub's completion is the end of this system's
confirmed scope, not a handoff to a further undisclosed downstream process,
so "attempted" would misstate what's known here (see /review Pass 1).

Per the locked scope exclusion (Case Study Section 6.5), CRM staleness or
scheduling conflicts are not modeled — this stub assumes success.
"""

from mock_data import mock_dealer_crm


def complete_scheduling(explanation_result):
    """Takes explain.py's output dict and writes the appointment to the
    mock dealer CRM. Always succeeds — no halt condition is modeled here,
    per the locked scope exclusion above."""
    action_plan = explanation_result["action_plan"]

    vehicle_record = mock_dealer_crm.find_vehicle_by_model(action_plan["vehicle_mention"])
    if vehicle_record is None:
        # [DEV] Fallback for a vehicle mention with no matching CRM record.
        # Not a modeled failure mode — the confirmed record gives this stub
        # no disclosed behavior for this case, so it degrades gracefully
        # rather than inventing a halt condition that isn't sourced.
        vehicle_record = {"vin": "UNKNOWN", "dealer_name": "Unknown Dealer"}

    confirmation = mock_dealer_crm.schedule_test_drive(
        vehicle_record,
        action_plan.get("requested_date"),
        action_plan.get("requested_time"),
    )

    return {
        "status": "scheduling_complete",
        "stage": "schedule_handoff",
        "reason": None,
        "confirmation": confirmation,
        "explanation_text": explanation_result["explanation_text"],
    }
