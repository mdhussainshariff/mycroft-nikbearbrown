"""
WHAT THIS FILE DOES: Provides fabricated dealer inventory/CRM records and a
mock "write" operation for scheduling a test drive. Consumed only by
schedule_handoff.py (plus orchestrator.py, per the one locked fetch-boundary
exception — see /v2, capital-one-v2-dependency-mapping.md).

CONSTRUCTED IN FULL. No real dealer CRM integration exists anywhere in this
repository. Dealer data is assumed always current and complete — CRM
staleness/conflict handling is an explicit, deliberate scope exclusion per
Case Study Section 6.5, not a silent gap. This file does not simulate
double-booking, disconnected inventory, or any other staleness failure mode.

[DEV]: Every record below is fabricated. Replace with real integration
points if adapting this reference implementation beyond illustrative use.
"""

import copy

# [DEV] Fabricated dealer inventory. Assumed always current per scope
# exclusion above — no staleness/conflict simulation exists.
DEALER_INVENTORY = {
    "VIN-1001": {
        "make": "Toyota", "model": "Camry", "year": 2026,
        "dealer_name": "Metro Toyota", "status": "available",
    },
    "VIN-1002": {
        "make": "Honda", "model": "Civic", "year": 2025,
        "dealer_name": "Riverside Honda", "status": "available",
    },
    "VIN-1003": {
        "make": "Ford", "model": "Mustang", "year": 2026,
        "dealer_name": "Downtown Ford", "status": "sold",
    },
}


def get_vehicle_record(vin):
    """Returns a fresh copy of a vehicle record by VIN, or None if not found."""
    record = DEALER_INVENTORY.get(vin)
    return copy.deepcopy(record) if record is not None else None


def find_vehicle_by_model(model_name):
    """Looks up a vehicle record by model name (case-insensitive). Returns a
    fresh copy with 'vin' included, or None if no match. Matching by model
    name rather than VIN is deliberate: this pipeline never collects a VIN
    from the customer, only a vehicle mention parsed from natural language —
    consistent with Capital One's own framing that customers interact
    "without committing personal information upfront" (Case Study Section 2)."""
    for vin, record in DEALER_INVENTORY.items():
        if record["model"].lower() == model_name.lower():
            match = copy.deepcopy(record)
            match["vin"] = vin
            return match
    return None


def schedule_test_drive(vehicle_record, requested_date, requested_time):
    """Mock 'write' to the dealer CRM. Always succeeds — no staleness or
    conflict handling is modeled, per the locked scope exclusion. Returns a
    minimal confirmation object; this is the one function in this repository
    that represents a genuine side effect against external (mock) state.
    No customer name is required or stored — see find_vehicle_by_model's
    docstring for why."""
    return {
        "confirmation_id": f"CONF-{vehicle_record.get('vin', 'UNKNOWN')}",
        "vin": vehicle_record.get("vin", "UNKNOWN"),
        "dealer_name": vehicle_record.get("dealer_name", "Unknown Dealer"),
        "scheduled_date": requested_date,
        "scheduled_time": requested_time,
    }
