"""
Verifiable Intent record (Section 4, Step 5 of the case study's illustrated
workflow).

Confirmed: Mastercard's March 2026 Verifiable Intent announcement describes
creating a "tamper-resistant record of what a user authorized" -- described
elsewhere in Mastercard's materials as providing cryptographic proof of
authorization (Section 3.3). Section 3.3 also states directly that whether
this function is fully integrated into Agent Pay's production intent APIs,
as opposed to available only via specification and reference
implementation, is not resolved by any source this case study reviewed.

Constructed, and deliberately NOT cryptographic: this module produces a
plain Python dict standing in for a record, with no signing, hashing, or
tamper-evidence of any kind. Simulating real cryptographic tamper-evidence
would imply a level of technical fidelity to Mastercard's actual mechanism
that nothing in the public record supports -- Mastercard has not disclosed
the record's actual structure, signing scheme, or storage location. This
repository does not guess at any of that. See DD005.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class IntentRecord:
    agent_id: str
    consumer_id: str
    category: str
    merchant: str
    amount: float
    transaction_date: date
    authorized_via: str  # "within_configured_limits" | "authorization_gate"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def create_intent_record(
    agent_id: str,
    consumer_id: str,
    category: str,
    merchant: str,
    amount: float,
    transaction_date: date,
    authorized_via: str,
) -> IntentRecord:
    """
    Build an intent record for a transaction that is about to complete.

    This function is only ever called on the path to COMPLETED -- never
    for a rejected or escalated transaction. Mastercard's own framing of
    Verifiable Intent is a record of what WAS authorized, not a record of
    what was declined; this repository's orchestrator preserves that by
    construction, not by convention (see test_intent_record.py).
    """
    return IntentRecord(
        agent_id=agent_id,
        consumer_id=consumer_id,
        category=category,
        merchant=merchant,
        amount=amount,
        transaction_date=transaction_date,
        authorized_via=authorized_via,
    )
