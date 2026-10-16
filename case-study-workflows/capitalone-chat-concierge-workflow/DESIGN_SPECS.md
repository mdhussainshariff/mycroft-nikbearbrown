# Design Specs

Technical reference for each component in this pipeline: purpose, interface,
inputs/outputs, and explicit scope boundaries. For *why* certain choices were
made, see `docs/DESIGN_DECISIONS.md`. For a narrative walkthrough, see
`README.md`.

---

## Pipeline Shape

```
request ──► Intake ──► Plan ──► Validation Gate ──► Explain ──► Schedule Handoff
               │          │            │                            │
               ▼          ▼            ▼                            ▼
            reason=     reason=      reason=                     status=
         unparseable_  infeasible_  not_validated            scheduling_
           request     against_                                complete
                       business_
                       rules
```

Strict, linear, fail-fast, with **three halt conditions across three stages**
and one terminal success state. A request that fails at any stage never
reaches a later one: Plan is never called for an unparseable request, the
Validation Gate is never constructed for a plan that is infeasible against
business rules, and Explain is never reached for a plan the Gate did not
validate.

Each of those properties is asserted directly with mock spies rather than
inferred from the returned status. The suite also asserts that a missing
decision function raises `TypeError` and never reaches Schedule Handoff, and
that a malformed decision-function return raises `ValueError` and likewise
never reaches it — the test that proves the zero-default Gate cannot be
silently defeated by a bad caller.

**Five stages, matching Capital One's own disclosed sequence** — understand,
plan, validate, explain, CRM handoff (Capital One tech blog, Mar. 5 2025) —
without adding steps beyond what is confirmed.

Every halt and the terminal success state return one shared shape:

```
{"status": "halted" | "scheduling_complete", "stage": <str>, "reason": <code> | null}
```

Reason codes are a fixed enum — `unparseable_request`,
`infeasible_against_business_rules`, `not_validated` — chosen rather than free
text so tests assert against stable values. See `docs/DESIGN_DECISIONS.md` §8.

---

## `src/intake.py`

**Purpose.** Parse a natural-language request into a structured object, or halt
if it lacks the minimum structure to proceed.

**Interface.** `parse_request(raw_request: str) -> dict`

**Returns.** On success: `vehicle_mention`, `requested_date`, `requested_time`,
`raw_request`. On failure: a halt object with `reason="unparseable_request"`.

**Halts when** the input is empty or not a string, carries no test-drive
intent, or names no recognised vehicle.

**Scope.** CONFIRMED that the system "understand[s] natural language prompts."
The parsing logic, the completeness criteria and the parsed-request shape are
all CONSTRUCTED — no source discloses a request schema. No LLM call is made; a
deterministic keyword parser stands in.

**Boundary that matters.** `KNOWN_VEHICLES` is a fabricated recognition
vocabulary and is deliberately **not** the dealer CRM's inventory. This module
is not permitted to import `mock_data`, so the two lists can legitimately
disagree — which is what `schedule_handoff.py`'s fallback exists to absorb.

---

## `src/plan.py`

**Purpose.** Build an action plan from a parsed request and injected
scheduling constraints.

**Interface.** `build_plan(parsed_request: dict, scheduling_constraints: dict) -> dict`

**Halts when** a requested date falls on a blackout date or a non-operating
day, or a requested time falls outside operating hours —
`reason="infeasible_against_business_rules"`.

**Never halts on** structural incompleteness. That is Intake's job alone, and
Plan cannot re-check it because it never receives Intake's completeness
criteria.

**Scope.** CONFIRMED that the system "come[s] up with an action plan to execute
on those prompts." The action-plan shape and the feasibility check are
CONSTRUCTED. The two-file split between Intake and Plan is a buildability
decision, not a Capital One-confirmed architectural boundary.

---

## `src/validation_gate.py`

**Purpose.** Run two internal checks on an action plan, then defer the
accept/reject decision entirely to an externally supplied decision function.

**Interface.** `ValidationGate(decision_fn)` then
`.validate(action_plan, policy_rules) -> dict`

**Construction fails** with `TypeError` if `decision_fn` is `None`. There are
no built-in acceptance criteria: no confidence threshold, no dollar amount, no
approval default of any kind.

**Decision-function contract.** `decision_fn(hallucination_check_result,
policy_conformance_result) -> "validated" | "not_validated"`. It receives the
two check outcomes **only** — never the raw action plan. Any other return
value raises `ValueError`; an unrecognised value is never treated as an
implicit approval.

**Internal checks.** `_check_hallucination` verifies structural completeness of
the plan object. `_check_policy_conformance` checks the vehicle mention against
a restricted-vehicle list. Both are CONSTRUCTED stand-ins for the real
diagnostics.

**Scope.** CONFIRMED that both checks exist as distinct functions — "check for
hallucinations or errors" and "simulate the execution of the action plan and
determine if the outcome conforms to policies and business rules." The
zero-default design is DELIBERATELY ABSENT: no source discloses what should
count as good enough, so the gate does not invent an answer.

**Documented limitation.** `max_advance_booking_days` is defined in the
business rules and is **not enforced** here. Recorded rather than silently
ignored.

---

## `src/explain.py`

**Purpose.** Generate a natural-language explanation of a validated plan for
the customer.

**Interface.** `generate_explanation(action_plan: dict) -> dict`

**Returns.** `explanation_text` plus the `action_plan` it describes, so
`schedule_handoff.py` receives everything it needs without re-deriving
anything.

**Has no halt condition.** Not an oversight: no source discloses this step
failing, and inventing a failure mode here would add a scenario Capital One
never described.

**Scope.** CONFIRMED that this function "generate[s] and deliver[s] a natural
language detailed explanation of the plan to the customer." The wording
template is CONSTRUCTED; no LLM call is made. Pure function — never touches
`mock_data`, never performs the scheduling action itself.

---

## `src/schedule_handoff.py`

**Purpose.** Terminal stage. Write the appointment to the mock dealer CRM.

**Interface.** `complete_scheduling(explanation_result: dict) -> dict`

**Returns.** `status="scheduling_complete"`, `stage="schedule_handoff"`,
`reason=None`, plus `confirmation` and `explanation_text`.

**Always succeeds.** No halt condition is modelled, per the scope exclusion on
CRM staleness.

**The inline refusal.** When a vehicle mention has no matching CRM record —
possible by design, because Intake's vocabulary and the CRM's inventory are
separate lists — the stub degrades to a fallback record rather than inventing a
halt condition that is not sourced. This is the one refusal in the build that
sits in the executable path rather than in a docstring.

**Scope.** CONFIRMED that test-drive scheduling integrates with the dealer's
CRM as the terminal action for a validated plan. The internal mechanism is a
CONSTRUCTED stub; no real CRM protocol is modelled. Named
`scheduling_complete` rather than `handoff_attempted` because this stub's
completion is the end of the system's confirmed scope, not a handoff to a
further undisclosed process.

---

## `src/orchestrator.py`

**Purpose.** Run Intake → Plan → Validation Gate → Explain → Schedule Handoff
in strict fail-fast sequence.

**Interface.** `run_pipeline(raw_request: str, decision_fn) -> dict`

**Contains no business logic of its own.** It is the only module besides
`schedule_handoff.py` permitted to import `mock_data`, and the only module that
selectively injects `scheduling_constraints` (to Plan only) and `policy_rules`
(to the Validation Gate only). That selective injection is what keeps the Plan
halt and the Gate halt provably non-overlapping.

---

## `src/mock_data/`

**`mock_business_rules.py`** — scheduling constraints and policy rules, split
into two named sections so that each is injected to exactly one consumer.

**`mock_dealer_crm.py`** — fabricated dealer inventory and a mock write
operation. CONSTRUCTED IN FULL; no real CRM integration exists anywhere in this
repository. Dealer data is assumed always current and complete: staleness and
conflict handling are an explicit, deliberate scope exclusion, not a silent
gap. Double-booking, disconnected inventory and other staleness failure modes
are not simulated.

---

## Tests

Six files, **32 tests, all passing**, following this series' spy/mock
assertion pattern — proving sequencing rather than only final output shape.

| File | Asserts |
|---|---|
| `test_intake.py` | parse success and all three unparseable paths |
| `test_plan.py` | feasibility halts, and that structural checks are not repeated here |
| `test_validation_gate.py` | the full 2×2 check matrix, missing and malformed decision functions, and that the decision function receives only the two check outcomes |
| `test_explain.py` | explanation shape for full, partial and absent scheduling detail |
| `test_schedule_handoff.py` | CRM write arguments, and graceful fallback for an unrecognised vehicle |
| `test_orchestrator.py` | spy-verified sequencing: each halt stops the pipeline before the next stage runs |
