"""
Input validation.

This module was added after an adversarial testing pass (see
docs/DESIGN_DECISIONS.md, Decision 007, and Section 6 of the case study)
found three problems in the original build:

  1. A negative amount completed silently, as if it were an ordinary
     small purchase.
  2. float('nan') as an amount also completed silently: NaN comparisons
     in Python are always False, so `nan > spending_limit` never
     triggers the over-limit check, and the transaction falls through
     to WITHIN_LIMITS as if the amount had actually been checked and
     found acceptable. This is the more serious of the findings --
     consistent with this series' general rule (most explicit at
     CommBank and Lloyds) that a silent, plausible-looking wrong answer
     is a worse failure mode than a visible crash.
  3. A string amount or a non-date transaction_date crashed with an
     unhandled TypeError partway through permissions.py, rather than
     escalating cleanly.

A subsequent review pass found this module's own first version
had not actually closed every crash path it claimed to: `datetime.datetime`
is a SUBCLASS of `datetime.date` in Python, so a full datetime object
passed the original `isinstance(transaction_date, date)` check as "valid"
-- and then crashed downstream in permissions.py, which cannot compare a
plain `date` to a `datetime` with `<=`. That gap is closed below by
checking for, and rejecting, `datetime` instances explicitly, before the
general date check runs. The same review pass also found that a
whitespace-only string (" ") passed the original non-empty-string check,
since `" " != ""`; the fix now strips whitespace before comparing.

Two distinct reasons are used rather than one generic "bad input" reason,
for the same reason Lloyds' reference implementation kept
"malformed_query_input" separate from "unparseable_date_format": a date
that cannot be read is a different claim than "the rest of the input is
unusable," and collapsing the two would hide which specific thing was
wrong.
"""

import math
from datetime import date, datetime
from typing import Optional

from .permissions import normalise_category


def validate_transaction_input(
    agent_id,
    consumer_id,
    category,
    merchant,
    amount,
    transaction_date,
) -> Optional[str]:
    """
    Returns None if every field is well-formed. Otherwise returns the
    reason string for the FIRST problem found, in a fixed order:
    non-date-related fields are checked before the date field, so a
    transaction that is broken in multiple ways still gets one
    deterministic, reproducible reason rather than a reason that depends
    on which check happens to run first on a given call.
    """
    for field_name, value in (
        ("agent_id", agent_id),
        ("consumer_id", consumer_id),
        ("category", category),
        ("merchant", merchant),
    ):
        # .strip() == "" catches whitespace-only strings (" ") in addition
        # to the empty string -- added during a second review pass (Finding #9):
        # a bare `== ""` check let a garbage identifier consisting only of
        # spaces through as if it were a real one.
        if not isinstance(value, str) or value.strip() == "":
            return "malformed_transaction_input"

    # A category made only of separators ("-", "___", " - ") passes the
    # non-empty check above but has no canonical form at all: it would
    # normalise to "" and reach the permission check looking exactly like a
    # category the consumer never configured. Rejected here as malformed
    # (third review pass, DD012; see permissions.normalise_category).
    if normalise_category(category) == "":
        return "malformed_transaction_input"

    # bool is a subclass of int in Python -- True/False would otherwise
    # silently pass an `isinstance(amount, (int, float))` check as 1/0.
    # Explicitly excluded, the same guard Lloyds' pipeline applies to its
    # claimed-amount field.
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return "malformed_transaction_input"

    if isinstance(amount, float) and (math.isnan(amount) or math.isinf(amount)):
        return "malformed_transaction_input"

    if amount < 0:
        return "malformed_transaction_input"

    # datetime.datetime is a SUBCLASS of datetime.date in Python, so
    # `isinstance(transaction_date, date)` alone would let a full
    # datetime object through as "valid" -- and then crash later, in
    # permissions.py, when compared against a plain `date` with `<=`
    # (you cannot compare a date to a datetime). Found during a second
    # review pass (Finding #2), after the original adversarial pass had
    # already closed the string-typed-date crash but missed this one.
    # datetime must be checked and rejected FIRST, before the general
    # `isinstance(x, date)` check, precisely because it would otherwise
    # pass that check.
    if isinstance(transaction_date, datetime) or not isinstance(transaction_date, date):
        return "invalid_transaction_date"

    return None
