"""
WHAT THIS FILE DOES: Generates a natural-language explanation of a validated
action plan, for presentation to the customer. Pure function — never
touches mock_data, never performs the scheduling action itself (that's
schedule_handoff.py's job, kept separate per /v2's resolution). Has no halt
condition: no source discloses this step failing, and inventing one here
would add a scenario Capital One never described.

CONFIRMED: Capital One's own blog states this function "generate[s] and
deliver[s] a natural language detailed explanation of the plan to the
customer" (Capital One tech blog, Mar. 5, 2025).

CONSTRUCTED: The specific wording template below. No real LLM call is used;
a deterministic canned template stands in for the actual model, consistent
with every prior entry in this series.
"""


def generate_explanation(action_plan):
    """Takes an already-validated action_plan dict (never a rejected one —
    the orchestrator enforces this via Halt #3) and returns an explanation
    object carrying both the explanation text and the plan it describes, so
    schedule_handoff.py receives everything it needs without re-deriving
    anything."""
    vehicle = action_plan["vehicle_mention"].title()
    date = action_plan.get("requested_date")
    time = action_plan.get("requested_time")

    if date and time:
        schedule_clause = f"on {date} at {time}"
    elif date:
        schedule_clause = f"on {date}, at a time to be confirmed with the dealership"
    else:
        schedule_clause = "at a date and time to be confirmed with the dealership"

    explanation_text = (
        f"Your test drive for the {vehicle} is planned {schedule_clause}. "
        f"The dealership will contact you to confirm final details."
    )

    return {
        "explanation_text": explanation_text,
        "action_plan": action_plan,
    }
