# Design Decisions Log
## Capital One Chat Concierge Reference Implementation (Series Entry 12)

Every departure from series convention or the original blueprint, with rationale tied to source, engineering necessity, or series convention — per this series' standing rule that departures are logged, not silently absorbed.

---

## 1. Intake/Plan Two-File Split (CONSTRUCTED, `/v1`–`/v2`)

**Departure from:** The case study's own Section 4 treats the Intake/Plan boundary as an unresolved reading, not a Capital One-confirmed architectural split.

**Decision:** Built as two separate files anyway.

**Rationale:** A pipeline stage needs a defined handoff contract to be independently testable. Keeping Plan a pure function that receives an already-parsed request (rather than parsing raw text itself) required the boundary to exist somewhere. Same reasoning as DBS's four-to-five-stage shift: the split serves buildability, not an added claim about Capital One's actual architecture.

---

## 2. `schedule_handoff.py` Added as a New Terminal Module (`/v2`)

**Departure from:** The original blueprint's file layout, which had no module for CRM scheduling — Section 3.1's confirmed CRM-integration capability had nowhere to live.

**Decision:** New file, DBS `finalize_submit.py`-precedent shape — thin stub, no invented business logic.

**Rationale:** A confirmed final action needs a component; folding it into `explain.py` was considered and rejected (see #6 below) because it would have merged a pure function with a genuine side effect, defeating the ability to prove via spy assertion that scheduling only happens after explanation completes.

---

## 3. Gate Outcome Naming: `validated` / `not_validated`, Not `not_authorized` (`/v3`)

**Departure from:** This series' usual default (`not_authorized` at Lemonade, `not_approved` at HSBC, `not_cleared_for_finalization` at DBS).

**Decision:** `validated` / `not_validated`.

**Rationale:** The one entry in this series where the source material's own verb was directly available and used — Capital One's blog literally says "validate that plan to mitigate against hallucination and errors." Source-grounded, not a stylistic preference.

---

## 4. `mock_business_rules.py` Split Into Two Named Sections (`/review` Pass 5)

**Departure from:** The original single-fixture design, where both `plan.py` and `validation_gate.py` would have read from one undifferentiated business-rules object.

**Decision:** `scheduling_constraints` (consumed only by `plan.py`) and `policy_rules` (consumed only by `validation_gate.py`), with no shared consumer.

**Rationale:** After Halt #2 was redefined to check business-rule feasibility (see #7), both stages needed "business rules" input — but from a single undifferentiated fixture, that would have silently recreated the exact duplicated-validation-ownership problem the Halt #2 fix was meant to eliminate, one layer down.

---

## 5. Validation Gate's Decision Function Receives Check Outcomes Only, Never the Raw Plan (`/review` Pass 5)

**Departure from:** No prior default existed on this point — this was an open design question, not a series convention.

**Decision:** The externally supplied decision function's signature is locked to `(hallucination_check_result, policy_conformance_result)`. It never receives the action plan itself.

**Rationale:** Directly contested during design review — the alternative ("both plan and check outcomes") was proposed and rejected because it would let a decision function implicitly weigh plan content over the check results, contradicting the blueprint's own stated test posture: "a contract test, not a business-rule test... since there is nothing to test *should* approve a plan." Giving the decision function the plan itself would have made that claim false in practice.

---

## 6. Terminal Success Status: `scheduling_complete`, Not `handoff_attempted` (`/review` Pass 1)

**Departure from:** DBS's `finalize_submit.py` precedent, which used `handoff_attempted`.

**Decision:** `scheduling_complete`.

**Rationale:** DBS's stub genuinely hands off to a separate, undisclosed downstream credit-approval process — "attempted" flags real uncertainty about what happens next. Capital One's `schedule_handoff.py` has no equivalent undisclosed downstream step; per the confirmed record, CRM scheduling completion is the end of this system's scope. Reusing DBS's name would have borrowed semantics that don't apply here. This was caught as a genuine naming bug during review, not chosen deliberately at first — logged here as much as a caution against copying prior-entry naming without re-deriving it.

---

## 7. Halt #2 Redefined: Business-Rule Infeasibility Only, Not "Cannot Construct a Plan" (`/review` Pass 3)

**Departure from:** The original blueprint's vaguer framing ("Plan cannot construct any action plan from the parsed request"), which overlapped with Intake's own structural completeness check.

**Decision:** Halt #2 now fires only when a structurally complete request (per Intake) is infeasible against `scheduling_constraints` — a check Intake structurally cannot perform, since it never receives that object.

**Rationale:** Two stages checking the same condition twice is not defense in depth here — it's duplicated validation ownership, and it also means two tests would have been indistinguishable from each other, proving nothing new.

---

## 8. Status Object Contract, With Fixed Reason-Code Enum (`/review` Pass 2 and Pass 5)

**Decision:** Every halt condition and the terminal success state return one shared shape:
```
{"status": "halted" | "scheduling_complete", "stage": <str>, "reason": <one of three fixed codes> | null}
```

**Rationale:** Before this was defined, "returns a status object" was unspecified across three different halt conditions — an ambiguous-return-contract gap of exactly the kind that has caused problems in prior entries. Reason codes were locked to a fixed enum (`unparseable_request`, `infeasible_against_business_rules`, `not_validated`) rather than free text, so tests assert against stable values, not prose that might be reworded later.

---

## 9. Customer Name Not Collected or Required Anywhere in This Pipeline (build-time decision, not pre-specified in `/v3`)

**Decision:** `mock_dealer_crm.schedule_test_drive` does not take a customer name parameter. Vehicles are matched by model name parsed from natural language, not by VIN or any customer-identifying field.

**Rationale:** This wasn't specified at design time and surfaced only once code had to actually run — logged here rather than silently patched in, per this series' discipline that real bugs/gaps found during build get flagged, not quietly fixed. It also turned out to align with the case study's own framing: Capital One's blog explicitly describes the customer interacting "without committing personal information upfront" (Section 2). Requiring a customer name to complete scheduling would have cut against that framing; not requiring one is a defensible reading of the confirmed record, not just a convenient shortcut — but it is a decision made during implementation, not one that was reviewed at `/v3`, and is flagged as such.

---

## 10. `intake.py`'s Vehicle-Recognition Vocabulary Is Separate From the CRM's Actual Inventory

**Decision:** `intake.py` maintains its own small, fabricated `KNOWN_VEHICLES` list, entirely independent of `mock_dealer_crm.py`'s `DEALER_INVENTORY`.

**Rationale:** Direct consequence of the locked fetch-boundary rule (`/v2`): Intake is not permitted to import `mock_data`. A real system would likely resolve vehicle mentions against live inventory; this stand-in exists only so Intake remains a pure function. Documented as a known limitation in the README, not silently assumed.

---

## 11. Known, Documented Limitation: `max_advance_booking_days` Is Defined but Not Enforced

`policy_rules["max_advance_booking_days"]` exists in the mock fixture but no check in `validation_gate.py` currently enforces it. Left in deliberately as a documented gap rather than removed or silently implemented, since implementing it would require inventing a "today" reference point not grounded in any source and not central to what this build exists to illustrate (the zero-default gate itself).
