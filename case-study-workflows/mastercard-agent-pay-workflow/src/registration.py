"""
Registration / verification check (Section 4, Step 2 of the case study's
illustrated workflow).

Confirmed: Mastercard's Agent Pay Acceptance Framework requires agents to be
"registered and verified" before they can transact (Section 3.2, sourced to
Mastercard's Oct 14, 2025 "Agentic token framework" page). An unregistered or
unverifiable agent is a hard stop -- rejected outright, not escalated to the
consumer for a decision -- because registration is a network-level
precondition, not something the consumer approves case by case (see the
case study's Section 4, Step 2, and DD001 below).

Constructed: the actual registration/verification check here is a lookup
against fabricated mock data, not a real Web Bot Auth signature validation.
Mastercard does not disclose what a real verification check looks like at
the protocol level; this module treats it as an opaque boolean, deliberately,
so it does not imply cryptographic detail the public record doesn't support.
"""

from dataclasses import dataclass

from . import mock_data


@dataclass(frozen=True)
class RegistrationResult:
    registered: bool
    verified: bool
    consumer_id: str | None
    reason: str | None  # None if both checks pass


def check_registration(agent_id: str) -> RegistrationResult:
    """
    Look up an agent_id against the mock registered-agent directory.

    Returns a RegistrationResult with reason=None only if the agent is both
    registered and verified. Otherwise reason is one of:
      - "unregistered_agent": the agent_id has no entry at all (or an
        explicitly None entry, standing in for "the network has never
        seen this agent").
      - "unverified_agent": the agent is registered but its verification
        flag is False.
    """
    entry = mock_data.REGISTERED_AGENTS.get(agent_id)

    if entry is None:
        return RegistrationResult(
            registered=False,
            verified=False,
            consumer_id=None,
            reason="unregistered_agent",
        )

    if not entry["registered"]:
        return RegistrationResult(
            registered=False,
            verified=False,
            consumer_id=None,
            reason="unregistered_agent",
        )

    if not entry["verified"]:
        return RegistrationResult(
            registered=True,
            verified=False,
            consumer_id=entry["consumer_id"],
            reason="unverified_agent",
        )

    return RegistrationResult(
        registered=True,
        verified=True,
        consumer_id=entry["consumer_id"],
        reason=None,
    )
