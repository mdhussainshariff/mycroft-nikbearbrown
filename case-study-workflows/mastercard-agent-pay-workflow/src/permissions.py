"""
Permission / limit check (Section 4, Step 3 of the case study's illustrated
workflow).

Confirmed: Mastercard's own August 2026 Signals materials describe Agentic
Tokens as configurable -- "restrictable by agent, merchant, category,
spending limit, timeframe or usage rules" (Section 3.2). No Mastercard
source discloses what happens if a consumer has not configured a given
category at all.

Constructed: this module's specific outcome taxonomy -- WITHIN_LIMITS,
OUTSIDE_LIMIT, OUTSIDE_TIMEFRAME, UNCONFIGURED -- is this repository's own
invention. The load-bearing design choice is keeping UNCONFIGURED separate
from OUTSIDE_LIMIT: an actively-set limit being exceeded is an unambiguous
policy violation (escalate, no gate needed), while a category the consumer
never configured one way or the other is genuinely ambiguous (route to the
Authorization Gate). Collapsing the two into one "denied" outcome would
hide that distinction -- see DD002 and DD003 in docs/DESIGN_DECISIONS.md.
"""

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum, auto

from . import mock_data


class PermissionOutcome(Enum):
    WITHIN_LIMITS = auto()
    OUTSIDE_LIMIT = auto()
    OUTSIDE_TIMEFRAME = auto()
    UNCONFIGURED = auto()


@dataclass(frozen=True)
class PermissionResult:
    outcome: PermissionOutcome
    reason: str | None  # None only for WITHIN_LIMITS


def normalise_category(category: str) -> str:
    """
    Canonical spelling of a category label, so the permission lookup can't
    mistake a configured category written differently for a category the
    consumer never configured (added during a third review pass; see
    docs/DESIGN_DECISIONS.md, Decision 012).

    Before this, the lookup was an exact string match on a label the agent
    itself supplies. "Household_Staples", "household_staples " and
    "household-staples" all missed Devon's configured "household_staples"
    entry, came back UNCONFIGURED, and went to the Authorization Gate -- so a
    transaction outside a timeframe Devon actively set could complete, as
    if Devon had never set one.

    Scope, stated deliberately: this normalises SPELLING only -- surrounding
    whitespace, letter case, and whether words are joined by spaces, hyphens
    or underscores. It does not map synonyms ("groceries" is still a
    different label from "household_staples"), because deciding which
    labels mean the same thing, or deriving a category from the merchant,
    would mean inventing a mechanism Mastercard has not disclosed. The
    category remains a label the agent asserts, not one this pipeline
    verifies -- see README.md, "Known limitations".
    """
    return "_".join(re.split(r"[\s_\-]+", category.strip().casefold())).strip("_")


def check_permissions(
    consumer_id: str,
    agent_id: str,
    category: str,
    amount: float,
    transaction_date: date,
) -> PermissionResult:
    """
    Check a proposed transaction against the consumer's configured
    permissions for this (consumer_id, agent_id) pair.

    Order of checks matters and is fixed deliberately, not incidentally:
    a category that was never configured at all is checked FIRST, before
    any limit or timeframe comparison is attempted -- there is nothing to
    compare an amount against if no permission entry exists for the
    category in the first place. This mirrors the same "don't evaluate a
    record you don't have" discipline this series applied at CommBank
    (Step 3 escalating on incomplete claim details before attempting a
    record lookup) and Zurich (contradiction check before policy fetch).
    """
    consumer_permissions = mock_data.CONSUMER_PERMISSIONS.get(
        (consumer_id, agent_id), {}
    )
    # Configured keys are compared in the same canonical spelling as the
    # incoming label (third review pass, DD012), so neither side's spelling decides it.
    category_permission = {
        normalise_category(k): v for k, v in consumer_permissions.items()
    }.get(normalise_category(category))

    if category_permission is None:
        return PermissionResult(
            outcome=PermissionOutcome.UNCONFIGURED,
            reason="unconfigured_category",
        )

    if not (
        category_permission["active_from"]
        <= transaction_date
        <= category_permission["active_until"]
    ):
        return PermissionResult(
            outcome=PermissionOutcome.OUTSIDE_TIMEFRAME,
            reason="outside_timeframe",
        )

    if amount > category_permission["spending_limit"]:
        return PermissionResult(
            outcome=PermissionOutcome.OUTSIDE_LIMIT,
            reason="outside_spending_limit",
        )

    return PermissionResult(outcome=PermissionOutcome.WITHIN_LIMITS, reason=None)
