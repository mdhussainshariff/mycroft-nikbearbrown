"""
WHAT THIS FILE DOES: Builds an action plan from an already-parsed request and
an injected scheduling_constraints object. Halts only on business-rule
infeasibility (a requested day/time the mock dealership doesn't operate on)
— never on structural incompleteness, which is Intake's job alone and which
Plan cannot re-check, since it never receives Intake's completeness
criteria. Pure function: does not import mock_data (see the locked
fetch-boundary rule in /v2).

CONFIRMED: Capital One's own blog states this function "come[s] up with an
action plan to execute on those prompts" (Capital One tech blog, Mar. 5,
2025); VentureBeat separately describes it as building "an action plan based
on business rules and the tools it is allowed to use."

CONSTRUCTED: The action-plan object's shape, and the specific feasibility
check against scheduling_constraints, are this repository's own invention.
The CONSTRUCTED two-file split between intake.py and plan.py is logged as a
buildability decision in docs/DESIGN_DECISIONS.md, not a Capital One-
confirmed architectural boundary.
"""

from datetime import datetime
import re

_TIME_PATTERN = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)


def build_plan(parsed_request, scheduling_constraints):
    """Builds an action plan dict, or a halt status object if the request
    (already confirmed structurally complete by Intake) is infeasible
    against scheduling_constraints."""
    requested_date = parsed_request.get("requested_date")
    requested_time = parsed_request.get("requested_time")

    if requested_date is not None:
        if requested_date in scheduling_constraints["blackout_dates"]:
            return _halt()
        weekday_name = _weekday_name(requested_date)
        if weekday_name is None or weekday_name not in scheduling_constraints["operating_days"]:
            return _halt()

    if requested_time is not None:
        if not _time_within_operating_hours(requested_time, scheduling_constraints["operating_hours"]):
            return _halt()

    return {
        "action": "schedule_test_drive",
        "vehicle_mention": parsed_request["vehicle_mention"],
        "requested_date": requested_date,
        "requested_time": requested_time,
    }


def _weekday_name(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
    except (ValueError, TypeError):
        return None


def _time_within_operating_hours(time_str, operating_hours):
    requested_minutes = _to_minutes(time_str)
    if requested_minutes is None:
        return True  # unparseable time string — not this stage's job to reject; Intake already accepted it
    open_minutes = _to_minutes(operating_hours["open"])
    close_minutes = _to_minutes(operating_hours["close"])
    return open_minutes <= requested_minutes <= close_minutes


def _to_minutes(time_str):
    match = _TIME_PATTERN.fullmatch(time_str.strip())
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3).lower()
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        return hour * 60 + minute
    # 24-hour "HH:MM" format, used by operating_hours constants
    if re.fullmatch(r"\d{1,2}:\d{2}", time_str.strip()):
        hour, minute = time_str.strip().split(":")
        return int(hour) * 60 + int(minute)
    return None


def _halt():
    return {
        "status": "halted",
        "stage": "plan",
        "reason": "infeasible_against_business_rules",
    }
