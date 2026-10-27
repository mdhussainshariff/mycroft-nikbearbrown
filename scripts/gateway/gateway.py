"""Route, call, check, and retry once. The whole request path in one place.

The retry rule, in full:

  - A failed check, or a provider error the adapter marked retryable, earns
    ONE retry on the escalation tier. Never a second. There is no loop here,
    so a chain is structurally impossible rather than merely discouraged.
  - A provider error marked terminal (bad key, unknown model) is never
    retried: every tier shares one credential, so it would fail identically.
  - A request already on the top tier has nowhere to escalate, so it stops.

What a retry can and cannot fix: the checks are free and only see an answer's
shape. A model that misreads sarcasm returns an allowed label, passes, and is
never retried. Retries recover malformed answers and flaky providers -- not
wrong answers (FINDINGS.md section 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gateway import prompts, validators
from gateway.adapters.base import LLMResponse, ProviderError
from gateway.client import GatewayClient
from gateway.policy import Policy
from gateway.router import RoutingDecision, route
from gateway.tiers import TierConfig


@dataclass(frozen=True)
class GatewayResult:
    """One logical request: what was tried, what came back, what it cost."""

    request_id: str
    task_type: str
    decision: RoutingDecision
    records: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    passed: bool = False
    error: str | None = None

    @property
    def escalated(self) -> bool:
        return len(self.records) > 1

    @property
    def attempts(self) -> int:
        return len(self.records)

    @property
    def final_tier(self) -> str | None:
        return self.records[-1]["tier"] if self.records else None

    @property
    def total_cost_usd(self) -> float:
        return sum(r["cost_usd"] for r in self.records)

    @property
    def total_latency_ms(self) -> int:
        return sum(r["latency_ms"] for r in self.records)


class Gateway:
    def __init__(self, *, client: GatewayClient, policy: Policy,
                 tiers: TierConfig, caller: str) -> None:
        self.client = client
        self.policy = policy
        self.tiers = tiers
        self.caller = caller

    def handle(self, *, task_type: str, text: str,
               context: list[str] | None = None,
               required_keys: list[str] | None = None) -> GatewayResult:
        decision = route(task_type=task_type, text=text,
                         policy=self.policy, tiers=self.tiers)
        rule = self.policy.rule_for(task_type)
        prompt = prompts.build(rule, text, context=context, required_keys=required_keys)

        def checker(max_tokens: int):
            def check(response: LLMResponse) -> dict[str, Any]:
                return validators.check(
                    rule["validator"], response.text,
                    tokens_out=response.tokens_out, max_tokens=max_tokens,
                    labels=rule.get("labels"), required_keys=required_keys,
                    input_text=text, context=context)
            return check

        records: list[dict[str, Any]] = []
        request_id = self.client.logbook.begin_request(
            task_type=task_type, caller=self.caller)

        # -- first attempt ------------------------------------------------
        try:
            first = self.client.call(
                task_type=task_type, caller=self.caller, tier=decision.tier,
                prompt=prompt, max_tokens=decision.max_tokens,
                request_id=request_id, routing_reason="policy",
                check=checker(decision.max_tokens), notes=decision.explanation)
        except ProviderError as exc:
            records = self._records_for(request_id)
            if not exc.retryable or decision.escalate_to is None:
                return GatewayResult(request_id=request_id, task_type=task_type,
                                     decision=decision, records=records,
                                     error=str(exc))
            return self._retry(request_id, task_type, decision, prompt, checker,
                               records, why=f"provider error: {exc}")

        records = self._records_for(request_id)
        if first.passed or decision.escalate_to is None:
            return GatewayResult(request_id=request_id, task_type=task_type,
                                 decision=decision, records=records,
                                 text=first.response.text, passed=first.passed)

        reason = (first.validator_result or {}).get("reason", "check failed")
        return self._retry(request_id, task_type, decision, prompt, checker,
                           records, why=f"check failed: {reason}")

    # -- the one retry ----------------------------------------------------

    def _retry(self, request_id: str, task_type: str, decision: RoutingDecision,
               prompt: str, checker, records: list[dict[str, Any]],
               why: str) -> GatewayResult:
        tier = decision.escalate_to
        max_tokens = self.policy.max_tokens(tier)
        try:
            second = self.client.call(
                task_type=task_type, caller=self.caller, tier=tier,
                prompt=prompt, max_tokens=max_tokens, request_id=request_id,
                routing_reason="escalation", check=checker(max_tokens),
                notes=f"retry after {why}")
        except ProviderError as exc:
            return GatewayResult(request_id=request_id, task_type=task_type,
                                 decision=decision,
                                 records=self._records_for(request_id),
                                 error=str(exc))

        return GatewayResult(request_id=request_id, task_type=task_type,
                             decision=decision,
                             records=self._records_for(request_id),
                             text=second.response.text, passed=second.passed)

    def _records_for(self, request_id: str) -> list[dict[str, Any]]:
        from gateway.report import by_request, read_records
        rows = by_request(read_records(self.client.logbook.writer.path))
        return rows.get(request_id, [])