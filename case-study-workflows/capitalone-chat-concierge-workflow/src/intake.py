"""
WHAT THIS FILE DOES: Parses a natural-language customer request into a
structured object, or halts with a status object if the request lacks the
minimum structure to proceed. Pure function — does not import mock_data,
per the fetch-boundary convention locked in /v2.

CONFIRMED: Capital One's own blog states this system's first function is to
"understand natural language prompts" (Capital One tech blog, Mar. 5, 2025).

CONSTRUCTED: The specific parsing logic, the completeness criteria, and the
parsed-request object's shape are all this repository's own invention — no
source discloses a request schema. No real LLM call is used anywhere in this
file; a small deterministic keyword parser stands in for the actual model,
consistent with every prior entry in this series.

[DEV]: KNOWN_VEHICLES below is a fabricated recognition vocabulary, entirely
separate from the dealer CRM's actual inventory (intake.py is not permitted
to import mock_data — see the locked fetch-boundary rule). A real system
would resolve vehicle mentions against live inventory; this stand-in exists
only so intake.py can be tested as a pure function.
"""

import re

# [DEV] Fabricated recognition vocabulary — not the same as CRM inventory.
KNOWN_VEHICLES = [
    "camry", "civic", "mustang", "corolla", "accord", "cr-v", "rav4",
]

TEST_DRIVE_INTENT_PATTERN = re.compile(r"\btest\s*drive\b", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
TIME_PATTERN = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))\b")


def parse_request(raw_request):
    """Parses raw_request (str). Returns a parsed-request dict on success,
    or a halt status object (per the shared status-object contract) if the
    request is unparseable — missing a recognizable vehicle or a test-drive
    scheduling intent."""
    if not raw_request or not isinstance(raw_request, str):
        return _halt()

    text = raw_request.strip()
    if not text:
        return _halt()

    if not TEST_DRIVE_INTENT_PATTERN.search(text):
        return _halt()

    vehicle = _extract_vehicle(text)
    if vehicle is None:
        return _halt()

    date_match = DATE_PATTERN.search(text)
    time_match = TIME_PATTERN.search(text)

    return {
        "vehicle_mention": vehicle,
        "requested_date": date_match.group(1) if date_match else None,
        "requested_time": time_match.group(1) if time_match else None,
        "raw_request": text,
    }


def _extract_vehicle(text):
    lowered = text.lower()
    for vehicle in KNOWN_VEHICLES:
        if vehicle in lowered:
            return vehicle
    return None


def _halt():
    return {
        "status": "halted",
        "stage": "intake",
        "reason": "unparseable_request",
    }
