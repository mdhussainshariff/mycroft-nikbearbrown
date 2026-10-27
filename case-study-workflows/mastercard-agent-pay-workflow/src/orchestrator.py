"""
Orchestrator for the Agent Pay reference pipeline.

Runs, in strict fail-fast sequence:
  0. Input validation (validation.py)
  1. Registration/verification check (registration.py)
  1b. Agent-consumer ownership check -- confirms the agent's actual
      registered owner matches the consumer_id the caller claims it is
      acting for (added during a second review pass; see Finding #1 and
      docs/DESIGN_DECISIONS.md, Decision 009)
  2. Permission/limit check (permissions.py), on the category's canonical
     spelling (added during a third review pass; see
     docs/DESIGN_DECISIONS.md, Decision 012)
  3. Authorization Gate -- ONLY if permissions.py returns UNCONFIGURED
     (gate.py)
  4. Verifiable Intent record creation -- ONLY on the path to completion
     (intent_record.py)

This is a single, linear pipeline, not a multi-agent system, matching what
Mastercard's public record actually supports: a small number of confirmed
functions (registration/verification, consumer-configured permissions,
human referral for ambiguous or out-of-policy cases, an intent record for
completed transactions) -- not a documented multi-agent architecture.

The Gate is instantiated once, at TransactionPipeline construction time,
and its constructor raises immediately if not given a valid decision
function -- so a pipeline built without a real authorization policy fails
at construction, before it ever processes a transaction, rather than
failing partway through Devon's purchase after registration and permission
checks have already run.
"""

from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from . import permissions, registration
from .gate import AuthorizationGate
from .intent_record import IntentRecord, create_intent_record
from .permissions import PermissionOutcome
from .validation import validate_transaction_input


@dataclass(frozen=True)
class TransactionResult:
    status: str  # "REJECTED" | "ESCALATED" | "COMPLETED"
    reason: Optional[str]
    intent_record: Optional[IntentRecord] = None


class TransactionPipeline:
    def __init__(self, gate_decision_fn: Callable[[dict], bool]):
        # Raises TypeError immediately if gate_decision_fn is missing or
        # not callable. See gate.py for why this is deliberate.
        self._gate = AuthorizationGate(gate_decision_fn)

    def process_transaction(
        self,
        agent_id: str,
        consumer_id: str,
        category: str,
        merchant: str,
        amount: float,
        transaction_date: date,
    ) -> TransactionResult:
        # --- Step 0: Input validation (added after the adversarial pass) -
        # Runs before anything else -- including before the registration
        # check -- because a malformed amount or date is not a real
        # transaction attempt to evaluate at all. See validation.py.
        validation_reason = validate_transaction_input(
            agent_id, consumer_id, category, merchant, amount, transaction_date
        )
        if validation_reason is not None:
            return TransactionResult(status="REJECTED", reason=validation_reason)

        # --- Step 1: Registration / verification ------------------------
        reg_result = registration.check_registration(agent_id)
        if reg_result.reason is not None:
            # Rejected outright -- NOT escalated to the consumer. Section 4
            # of the case study is explicit that registration is a
            # network-level precondition, not a per-transaction consumer
            # decision. Permissions and the Gate are never touched.
            return TransactionResult(status="REJECTED", reason=reg_result.reason)

        # --- Step 1b: Agent-consumer ownership check ---------------------
        # Found during a second review pass (Finding #1), not by the original
        # adversarial pass: nothing previously compared the agent's
        # ACTUAL registered owner (reg_result.consumer_id) against the
        # consumer_id the caller claims the agent is acting for. Without
        # this check, an agent registered to one consumer could be used
        # to attempt a transaction "on behalf of" a completely different,
        # unrelated consumer_id -- and the pipeline would only see an
        # ordinary UNCONFIGURED category (that consumer/agent pair simply
        # has no permission entries), indistinguishable from a legitimate
        # new-category case, with no signal to the Gate that anything was
        # actually wrong. This is rejected outright, at the same stage and
        # for the same reason as any other registration-level failure --
        # ownership is a network-level fact, not something a per-
        # transaction decision function should have to infer from an
        # empty permissions lookup.
        if reg_result.consumer_id != consumer_id:
            return TransactionResult(status="REJECTED", reason="agent_consumer_mismatch")

        # --- Step 2: Permission / limit check ----------------------------
        # The category is put into its canonical spelling once, here, and
        # that form is what the permission check, the Gate and the
        # Verifiable Intent record all see (third review pass;
        # DD012). Without this, a configured category written differently
        # ("Household_Staples") looked exactly like a category the consumer
        # never configured, and bypassed the restriction they had set.
        category = permissions.normalise_category(category)
        perm_result = permissions.check_permissions(
            consumer_id=consumer_id,
            agent_id=agent_id,
            category=category,
            amount=amount,
            transaction_date=transaction_date,
        )

        if perm_result.outcome == PermissionOutcome.OUTSIDE_LIMIT:
            # Unambiguous policy violation -- escalates directly. The
            # Gate is never called for this outcome (see DD003).
            return TransactionResult(status="ESCALATED", reason=perm_result.reason)

        if perm_result.outcome == PermissionOutcome.OUTSIDE_TIMEFRAME:
            return TransactionResult(status="ESCALATED", reason=perm_result.reason)

        authorized_via = "within_configured_limits"

        if perm_result.outcome == PermissionOutcome.UNCONFIGURED:
            # --- Step 3: Authorization Gate (ambiguous case only) --------
            gate_context = {
                "agent_id": agent_id,
                "consumer_id": consumer_id,
                "category": category,
                "merchant": merchant,
                "amount": amount,
                "transaction_date": transaction_date,
            }
            approved = self._gate.decide(gate_context)
            if not approved:
                return TransactionResult(
                    status="ESCALATED", reason="not_authorized_by_gate"
                )
            authorized_via = "authorization_gate"

        # --- Step 4: Verifiable Intent record, then complete -------------
        intent_record = create_intent_record(
            agent_id=agent_id,
            consumer_id=consumer_id,
            category=category,
            merchant=merchant,
            amount=amount,
            transaction_date=transaction_date,
            authorized_via=authorized_via,
        )
        return TransactionResult(
            status="COMPLETED", reason=None, intent_record=intent_record
        )
