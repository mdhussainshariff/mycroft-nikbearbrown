# Capital One Chat Concierge Agentic Pipeline — Reference Implementation

**Status:** Built and tested. Seven modules (plus two mock-data fixtures), 32 passing tests across six test files, all asserting sequencing via spy/mock — not just final output shape — following this series' standard pattern.

**Source case study:** Capital One — Agentic AI in Retail Banking & Auto Finance (Series Entry 12). This reference implementation grounds the Chat Concierge test-drive-scheduling function described in the case study's Sections 3–4 and 6.

This repository is **not** a disclosure of Capital One's actual Chat Concierge system. See **Explicit Non-Claims** below before reading further.

---

## What This Is

Capital One's own tech blog (Mar. 5, 2025) describes Chat Concierge performing four functions via "multiple logical agents": understanding natural-language prompts, building an action plan, validating that plan against hallucination/error and policy-conformance checks, and generating a natural-language explanation before the plan reaches the customer. VentureBeat's reporting on Milind Naphade, SVP, Technology (AI Foundations), separately attributes a specific four-agent breakdown to this system — a secondary-source specification, not Capital One's own stated architecture, and the two are kept distinct throughout this repository.

That confirmed sequence — understand → plan → validate → explain — plus a confirmed terminal CRM-scheduling integration, is the entire factual basis for this build. Where Capital One's disclosure stops, this implementation stops too.

---

## Architecture

A single, linear, fail-fast pipeline — not four communicating agent processes simulating an architecture Capital One never disclosed:

```
Intake → Plan → Validation Gate → Explain → Schedule Handoff
```

**Halt map:**

| # | Condition | Halts before | Reason code |
|---|---|---|---|
| 1 | Intake cannot parse the request (no recognizable test-drive intent and vehicle mention) | Plan | `unparseable_request` |
| 2 | Request is structurally complete but infeasible against `scheduling_constraints` (blackout date, non-operating day, out-of-hours time) | Validation Gate | `infeasible_against_business_rules` |
| 3 | Validation Gate's decision function returns `not_validated` | Explain | `not_validated` |
| 4 | All conditions clear | — | Explain → Schedule Handoff run to `scheduling_complete` |

Halts #1 and #2 are deliberately non-overlapping: Intake checks structural completeness only; Plan checks business-rule feasibility only, using a `scheduling_constraints` object Intake never receives. This split was corrected during design review after the original halt conditions were found to overlap (see `docs/DESIGN_DECISIONS.md`, #7).

**Exceptions (misuse of the code, not domain outcomes):**
- Constructing `ValidationGate` without a decision function → `TypeError`
- A supplied decision function returning anything other than `validated` or `not_validated` → `ValueError` — the one place a badly written external function could otherwise silently defeat the gate by failing open.

**Status object contract** — every halt and the terminal success state share one shape:
```python
{"status": "halted" | "scheduling_complete", "stage": <str>, "reason": <one of three fixed codes> | None}
```

---

## Module Reference

| File | What it does | Confirmed / Constructed |
|---|---|---|
| `mock_data/mock_business_rules.py` | Two independent fixtures: `scheduling_constraints` (dealership hours/blackout dates, consumed only by `plan.py`) and `policy_rules` (consumed only by `validation_gate.py`). | CONSTRUCTED in full — no Capital One source discloses either. |
| `mock_data/mock_dealer_crm.py` | Fabricated dealer inventory, keyed by VIN, matched by model name. Assumed always current — no staleness simulated. | CRM-integration capability CONFIRMED (Section 3.1); internal records CONSTRUCTED. |
| `intake.py` | Parses natural-language request via a deterministic keyword parser (no real LLM call). Halts if no test-drive intent or recognizable vehicle mention. | Function CONFIRMED ("understand natural language prompts"). Parsing logic, completeness criteria, and vehicle vocabulary CONSTRUCTED. |
| `plan.py` | Builds an action plan from Intake's output and `scheduling_constraints`. Halts only on business-rule infeasibility. | Function CONFIRMED ("come up with an action plan"). Feasibility check and plan shape CONSTRUCTED. The Intake/Plan two-file split itself is a CONSTRUCTED buildability decision (see `docs/DESIGN_DECISIONS.md`, #1). |
| `validation_gate.py` | Runs a hallucination/error check and a policy-conformance check, then defers entirely to an externally supplied decision function. **Zero built-in acceptance criteria — the deliberately-absent-default component this build exists to illustrate.** | Both checks CONFIRMED as distinct functions. Zero-default design grounded in Naphade's own governance-gap framing (VentureBeat, Jul. 2025). |
| `explain.py` | Pure function; generates a natural-language explanation of a validated plan. Never touches mock data, never fails. | Function CONFIRMED ("generate and deliver a natural language detailed explanation"). Template CONSTRUCTED. |
| `schedule_handoff.py` | Terminal stub. Writes the appointment to the mock dealer CRM. Added during `/v2` — the original blueprint's file layout had no module for this confirmed capability. | CRM-integration CONFIRMED (Section 3.1). Stub mechanism CONSTRUCTED. |
| `orchestrator.py` | Runs all five stages in strict fail-fast sequence; the only module (besides `schedule_handoff.py`) that touches `mock_data`, and the only one that selectively injects `scheduling_constraints`/`policy_rules`. | Mirrors Capital One's disclosed sequence without adding steps. |

---

## Naming: Why `validated` / `not_validated`, Not `not_authorized`

This series has generally used `not_authorized` (Lemonade), `not_approved` (HSBC), or `not_cleared_for_finalization` (DBS) as its convention for a rejected outcome. This build departs from that default and uses `validated` / `not_validated` instead — the one entry in this series where the source material supplies its own literal verb ("validate that plan to mitigate against hallucination and errors," Capital One tech blog). The naming is source-grounded, not a stylistic choice; see `docs/DESIGN_DECISIONS.md` #3 for the full rationale.

---

## What the Tests Prove

Following this series' spy/mock-assertion pattern — proving sequencing, not just final output — across 32 tests in six files:

- Unparseable input → `plan_module.build_plan` asserted **never called**.
- A blackout-date request → `ValidationGate` asserted **never constructed**.
- Validation Gate returning `not_validated` → `explain_module.generate_explanation` asserted **never called**.
- Missing decision function → `TypeError` propagates through the orchestrator's entry point, and `schedule_handoff.complete_scheduling` asserted **never called**.
- An unrecognized decision-function return value → `ValueError` propagates, `schedule_handoff.complete_scheduling` asserted **never called** — the test that proves the zero-default gate can't be silently defeated by a malformed caller.
- The full 2×2 hallucination-pass/fail × policy-pass/fail matrix, plus a spy-verified assertion that the decision function receives the two check outcomes only — never the raw plan (locked design decision, see `docs/DESIGN_DECISIONS.md` #5).
- A clean, complete request (the Camry/2026-10-05/2pm scenario) runs end-to-end to `scheduling_complete`, with a spy-verified assertion of the exact arguments passed to `mock_dealer_crm.schedule_test_drive`.
- An unrecognized vehicle mention degrades gracefully to a fallback CRM record rather than raising or halting — proving this isn't accidentally a modeled failure mode.

Run any test file directly (e.g. `python3 tests/test_orchestrator.py`) or as a suite via your test runner of choice.

---

## Known Limitations

- No real LLM call anywhere — Intake's parser and Explain's template are both deterministic stand-ins, consistent with every prior entry in this series.
- No real dealer CRM integration — mock data only, assumed always current; staleness and conflict handling are explicit scope exclusions, not silent gaps (Case Study Section 6.5).
- `policy_rules["max_advance_booking_days"]` is defined in the fixture but not currently enforced by any check — a documented gap, not a silent one (see `docs/DESIGN_DECISIONS.md` #11).
- `intake.py`'s vehicle-recognition vocabulary is separate from `mock_dealer_crm.py`'s actual inventory, a direct consequence of the locked rule that Intake cannot import mock data.
- This pipeline models one customer request's path through the system, not throughput at Capital One's actual scale.
- No customer-identifying information is collected or required anywhere in this pipeline — a design choice consistent with, though not literally specified by, Capital One's own framing that customers interact "without committing personal information upfront" (Case Study Section 2). See `docs/DESIGN_DECISIONS.md` #9.

---

## Explicit Non-Claims

This repository is not a disclosure of Capital One's actual Chat Concierge system. It does not claim to replicate Capital One's agent architecture, agent count, internal data schemas, request-type taxonomy, or Validation Gate acceptance criteria, and should not be cited as evidence of Capital One's technical design. Every CONSTRUCTED element above exists to make a testable reference implementation possible — not as a guess about what Capital One actually built.

---

*This README describes the implementation as built and tested, superseding the original pre-build blueprint's file layout and halt-condition framing where the two differ — see `docs/DESIGN_DECISIONS.md` for the full log of what changed during design review and why.*
