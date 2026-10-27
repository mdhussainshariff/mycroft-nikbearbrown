"""
Authorization Gate (Section 4, Step 4 of the case study's illustrated
workflow).

This is the repository's central design decision, and it follows the same
pattern this series used for Lemonade's Authorization Gate, HSBC's Human
Review Gate, Zurich's Authorization Gate for Clara, and Lloyds' Authorization
Gate for its financial assistant.

WHAT THIS GATE IS FOR: it is invoked only for the UNCONFIGURED case from
permissions.py -- a transaction in a category the consumer never configured
one way or the other. It is NOT invoked for OUTSIDE_LIMIT or
OUTSIDE_TIMEFRAME, which are unambiguous policy violations that escalate
directly without needing an external decision (see DD003).

WHAT IT DOES NOT SHIP WITH: any default rule for resolving that ambiguity.
No spending-limit cutoff, no "allow first-time categories under $X," no
confidence score, under any label, anywhere in this file. Mastercard
confirms only that agents transact within consumer-set permissions and
limits -- a category, not a boundary for what happens when no permission
was set at all. Inventing a labeled placeholder here ("[DEV] auto-approve
under $50") would have implied a shape of answer -- that Mastercard's real
system defaults to some safe-seeming allowance -- that nothing in the
public record supports. So the Gate raises, at construction, if it isn't
given a real decision function, and it validates that function's return
value strictly rather than silently coercing it.
"""

from typing import Callable


class AuthorizationGate:
    """
    Wraps an externally supplied decision function. The function receives
    a dict describing the ambiguous transaction and must return a plain
    bool: True to allow it to proceed, False to escalate it to the
    consumer.

    Raises TypeError at construction if decision_fn is missing or not
    callable -- deliberately, so a pipeline built without a real policy
    fails once, immediately, at construction, rather than partway through
    processing a transaction after registration and permission checks have
    already done real work. This mirrors the same fail-fast discipline
    Lloyds' Authorization Gate and Lemonade's Authorization Gate apply.
    """

    def __init__(self, decision_fn: Callable[[dict], bool]):
        if decision_fn is None or not callable(decision_fn):
            raise TypeError(
                "AuthorizationGate requires a callable decision_fn; "
                "none was supplied. This Gate ships with no default "
                "authorization criteria -- see gate.py module docstring."
            )
        self._decision_fn = decision_fn

    def decide(self, context: dict) -> bool:
        """
        Calls the supplied decision function with the ambiguous
        transaction's context and strictly validates the return value.

        Raises ValueError if the decision function returns anything other
        than a plain bool (explicitly rejecting truthy/falsy non-bool
        values such as 1, 0, "yes", or None, consistent with this
        series' practice of validating a Gate's contract rather than
        coercing an unexpected type into a decision).
        """
        decision = self._decision_fn(context)
        if not isinstance(decision, bool):
            raise ValueError(
                f"AuthorizationGate's decision_fn must return a plain "
                f"bool; got {type(decision).__name__} ({decision!r})."
            )
        return decision
