# Mastercard Agent Pay — Reference Pipeline (Illustrative Scaffold)

## What this is

This is a small, tested, runnable Python pipeline that illustrates how an
AI shopping agent's attempt to complete a purchase through **Mastercard
Agent Pay** might be checked before it either completes or gets sent back
to the human consumer for a decision.

It is a companion technical artifact to a case study on Mastercard's AI
and agentic-commerce initiatives — specifically **Decision Intelligence
Pro** (a generative AI enhancement to Mastercard's existing fraud-scoring
service) and **Agent Pay** (Mastercard's framework for AI-agent-initiated
payments, including Agentic Tokens, the Agent Pay Acceptance Framework,
and Verifiable Intent). It follows the same pattern every prior entry in
that case study series has used: build and test a reference
implementation, don't just describe one in prose.

**The single most important thing to understand about this repository:
every design choice in it traces back to something a public Mastercard
source actually said, or is explicitly labeled as this repository's own
invented construction filling a gap the public record does not address.**
This code was built entirely from Mastercard's own press releases,
newsroom pages, earnings-call transcripts, SEC filings, and standards-body
announcements (Cloudflare, FIDO Alliance, IETF) — plus reporting from
outlets like CNBC, Fortune, and Payments Dive quoting Mastercard
executives on the record. No non-public information about Mastercard's
actual systems was used, referenced, or assumed anywhere in this
repository, because none was available to build it from. Where Mastercard
has not disclosed how something actually works, this repository says so
directly, in the code's own comments and in this README, rather than
inventing a plausible-sounding mechanism to fill the gap.

## Why this exists

Mastercard's own public materials confirm a handful of specific functions
— agents must be registered and verified before they can transact;
consumer-configured permissions can restrict a token by agent, merchant,
category, spending limit, timeframe, or usage rule; a Verifiable Intent
record captures what a consumer authorized — without disclosing the
actual mechanics behind any of them: no real cryptographic protocol
implementation, no disclosed default for a category the consumer never
configured, no disclosed resolution rate for how often an agent-initiated
transaction completes without a human. Building and testing an actual
pipeline against exactly those confirmed functions — and no more — is how
this case study series checks that a narrative built from press releases
is internally consistent, rather than leaving it as prose that sounds
coherent but was never actually run.

## How the workflow works

A transaction moves through four numbered stages plus one unlabeled
sub-check, run by an orchestrator in strict, fail-fast sequence — meaning
each stage can stop the pipeline outright, and if it does, no later stage
ever runs. (One clarifying note on numbering: this README numbers stages
by what the code actually does, starting at Step 0. The case study's own
Section 4 numbers steps starting from "the agent attempts a transaction"
as Step 1 — the two documents describe the same flow but count
differently, since they serve different purposes; neither numbering is
wrong, and a reader moving between the two should expect the step numbers
not to line up one-to-one.)

```
Step 0: Input Validation
   |
   v  (only if input is well-formed)
Step 1: Registration / Verification Check
   |
   v  (only if the agent is registered AND verified)
Step 1b: Agent-Consumer Ownership Check
   |
   v  (only if the agent's real registered owner matches the claimed consumer)
Step 2: Permission / Limit Check
   |
   +--> WITHIN_LIMITS -------------------------> Step 4: Complete
   |
   +--> OUTSIDE_LIMIT / OUTSIDE_TIMEFRAME ------> Escalate to consumer
   |
   +--> UNCONFIGURED
          |
          v
       Step 3: Authorization Gate (no default -- requires an externally
                supplied decision function)
          |
          +--> Approved --------------------------> Step 4: Complete
          |
          +--> Not approved ----------------------> Escalate to consumer
```

**Step 0 — Input Validation** (`src/validation.py`). Checks that every
field describing the attempted transaction is actually usable: the
agent/consumer/category/merchant fields are non-empty strings, the amount
is a real, finite number that isn't negative, and the date is an actual
date object, and the category has a usable canonical form (a label made only of separators, such as
`"-"`, is malformed; see DD012). This step did not exist in the first version of this
repository — it was added after a deliberate adversarial testing pass
found that a negative amount and `NaN` both silently completed as if they
were ordinary valid transactions, and a string-typed amount or date
crashed the pipeline outright. See "What building it surfaced" below and
`docs/DESIGN_DECISIONS.md`, Decision 007.

**Step 1 — Registration / Verification Check** (`src/registration.py`).
Looks the agent up against a small, fabricated mock directory. Mastercard's
own language ("agents ... must be registered and verified before they can
transact") is treated as two separate preconditions, not one: an agent can
be registered but currently failing verification, or not registered at
all, and this pipeline gives those two states two different, distinctly
named failure reasons. Either failure is a hard rejection — not something
escalated to the consumer for a decision — because registration is a
network-level precondition in Mastercard's own framing, not a
per-transaction choice.

**Step 1b — Agent-Consumer Ownership Check** (`src/orchestrator.py`).
Confirms that the agent's *actual* registered owner matches the
`consumer_id` the caller claims it is transacting for. This check did not
exist in the original build — it was added after a second review pass
found that, without it, an agent genuinely registered to one consumer
could be used to attempt a transaction "on behalf of" a completely
different, unrelated consumer, and the pipeline would only see an ordinary
`UNCONFIGURED` category (that consumer/agent pair simply has no permission
entries), indistinguishable from a legitimate new-category case. A
mismatch is rejected outright, at the same stage and with the same
severity as any other registration-level failure — this is a fact about
who the network says an agent belongs to, not something a per-transaction
decision function should have to infer from an empty permissions lookup.

**Step 2 — Permission / Limit Check** (`src/permissions.py`). Compares the
proposed transaction against whatever the consumer has configured for
this specific agent. The category is first put into one canonical spelling
(case, surrounding whitespace, and spaces/hyphens/underscores between words
no longer matter), and the configured entries are compared the same way. This
was added after a third review pass found that `Household_Staples` missed a
configured `household_staples` entry and bypassed its restriction (DD012).
Synonyms are deliberately not mapped. Mastercard's own August 2026 materials confirm tokens
are restrictable "by agent, merchant, category, spending limit, timeframe
or usage rules" — this pipeline implements category, spending limit, and
an active date window, as one illustrative, non-exhaustive realization of
that confirmed list. The check deliberately looks for whether the category
was configured **at all** before it ever compares an amount or a date
against a limit — because there is nothing to compare against if no
permission entry exists for that category in the first place.

**Step 3 — Authorization Gate** (`src/gate.py`) — **the repository's
central design decision.** This step only ever runs for the one case that
is genuinely ambiguous under Mastercard's confirmed language: a category
the consumer never configured one way or the other. (An amount that
exceeds an actively-set limit, or a transaction outside an actively-set
timeframe, is unambiguous — it escalates directly, without ever reaching
this Gate.) The Gate ships with **zero default authorization criteria** —
no spending-limit cutoff, no category allowlist, no confidence score,
under any label, anywhere in this codebase. It requires a real, externally
supplied decision function before it will do anything at all, and it
raises an error immediately if one isn't supplied — at pipeline
construction time, not partway through processing a transaction. This
mirrors exactly how this series has handled the same kind of undisclosed
boundary at every prior entry (Lemonade's AI Jim settlement authority,
HSBC's coding-assistant review gate, Zurich's Clara authorization
boundary, Lloyds' financial-assistant escalation boundary).

**Step 4 — Verifiable Intent Record** (`src/intent_record.py`). For any
transaction that completes — whether because it was within the consumer's
configured limits, or because the Gate approved it — a record is created
capturing what was authorized. Mastercard's own language describes this as
a "tamper-resistant record" providing "cryptographic proof of
authorization." This implementation does not attempt real cryptography
(see `docs/DESIGN_DECISIONS.md`, Decision 005) — it produces a plain
Python object with the relevant fields, because Mastercard has not
disclosed the record's actual structure, signing scheme, or storage
location, and inventing one would overstate what's confirmed.

## What's confirmed vs. constructed vs. deliberately absent

**Confirmed** (sourced to Mastercard's own materials, cited in the case
study's Section 3):
- Agents must be registered and verified before they can transact.
- Agentic Tokens are configurable/restrictable by agent, merchant,
  category, spending limit, timeframe, or usage rule.
- Verifiable Intent creates a cryptographically verifiable record of what
  a consumer authorized.
- This is a small number of distinct functions performed by one system —
  not a documented multi-agent architecture. Consistent with that, this
  pipeline is a single, linear flow, not a multi-agent system.

**Constructed, and treated as illustrative rather than disclosed:**
- The mock registered-agent directory and its exact fields
  (`src/mock_data.py`).
- The specific permission schema (category → spending limit, active
  window, usage rule) — Mastercard confirms the *dimensions* a token can
  be restricted by; this repository's exact data structure for those
  dimensions is invented.
- The registration/verification check's implementation as a plain
  boolean lookup rather than a real cryptographic signature check.
- The Verifiable Intent record's exact fields and the fact that it is a
  plain Python object rather than a cryptographically signed artifact.
- The agent-consumer ownership check itself. Mastercard does not state,
  in these terms, that its network verifies an agent's claimed owner
  against its actual registered owner before evaluating permissions — but
  it is a reasonable baseline expectation for any system that lets an
  agent act "on behalf of" a specific consumer, and its absence in the
  original build was a genuine correctness gap, not merely an undisclosed
  mechanism. See `docs/DESIGN_DECISIONS.md`, Decision 009.

**Deliberately absent — no illustrative default at all:**
- The Authorization Gate's actual decision criteria. See Step 3 above and
  `docs/DESIGN_DECISIONS.md`, Decisions 003 and 004.

## Test coverage

The suite comprises **82 tests across 9 files**, run in full before this
repository was considered finished — 45 in the original build, 18 added
after the adversarial testing pass, a further 9 added after a second review
pass found one critical correctness gap and several smaller issues
the adversarial pass hadn't been aimed at, and 10 added after a third review
pass (DD012). **Result: 82 tests, 82 passing, 0 failing.** Verified three times in a freshly created, empty Python virtual
environment (confirmed via `pip list` to contain nothing beyond `pip`
itself) against a cache-free copy of the repository — once after the
adversarial pass, again after the second review pass's fixes, and again
after the third review pass's fixes (Python 3.12) — so the passing-
test claim reflects the code's actual behavior rather than leftover state
in the directory it was built in.

| Test file | What it proves |
|---|---|
| `test_validation.py` | Every field-level validation rule fires correctly and independently: negative amounts, `NaN`, infinite amounts, `bool`-typed amounts, `None` amounts, non-`date` transaction dates (including a `datetime.datetime` object, which is a subclass of `date` and would otherwise slip past a naive `isinstance` check), `None` categories, whitespace-only identifier fields, and empty-string identifier fields are each rejected with the correct, distinct reason; a genuinely valid transaction (including the `$0.00` edge case) is *not* flagged. |
| `test_registration.py` | Registered-and-verified agents pass; registered-but-unverified and never-registered agents fail with two distinct, non-colliding reasons. |
| `test_permissions.py` | All four permission outcomes (within limits, outside limit, outside timeframe, unconfigured) are independently reachable; the unconfigured check is proven to run *before* any limit comparison; the spending-limit boundary is checked exactly at the configured value; a transaction violating both the spending limit and the active timeframe at once is proven to deterministically resolve to `OUTSIDE_TIMEFRAME`, not `OUTSIDE_LIMIT`. |
| `test_gate.py` | The Gate's contract, not a business rule: raises on a missing, non-callable, or literal-`bool` `decision_fn`; honors both `True` and `False`; raises on any non-`bool` return value; passes the transaction context through unmodified. |
| `test_intent_record.py` | The record captures every relevant field; `authorized_via` correctly distinguishes a within-limits completion from a Gate-approved one. |
| `test_orchestrator_fail_fast.py` | Mock/spy assertions proving later stages are never called once an earlier stage has rejected or escalated a transaction — including that malformed input and an invalid date are both caught before the registration check ever runs; that an agent-consumer ownership mismatch is caught before the permission check or intent-record creation ever runs; that the Gate is never invoked for an unambiguous limit or timeframe violation, and is invoked exactly once for a genuinely unconfigured category; and that a pipeline built without a decision function fails at construction. |
| `test_escalation_reasons.py` | All eight terminal outcomes are each independently reachable with the correct status and reason attached, and all reason strings are confirmed pairwise distinct. |
| `test_category_normalisation.py` | Spelling variants of a configured category (case, surrounding whitespace, spaces/hyphens/underscores) resolve to the configured entry, so its timeframe and limit still apply; the exact finding (`Household_Staples`, $70, outside Devon's window) now escalates without ever reaching the Gate; the Gate context and the intent record carry the canonical category; a separator-only category is rejected as malformed; and a synonym (`groceries`) is still unconfigured, the deliberate scope boundary. |
| `test_happy_path.py` | Both fully-successful paths work end to end and correctly attach a Verifiable Intent record, including a second, independent consumer/agent pairing; all halt paths (rejected for any of three reasons, escalated) correctly leave no intent record behind. |

## What building it surfaced

This repository went through two separate rounds of scrutiny after its
first version passed all of its own tests (a third round, added later, is
recorded at the end of this section), and both rounds found real
problems — worth naming as two separate events, not blended into one
generic "issues were found and fixed" statement, because they were found
by different methods and have a different character.

### Round 1: an adversarial testing pass

The original version of this pipeline passed all 45 of its tests on the
first complete run. That was accurate, but narrower than it initially
read: a test suite only proves what it specifically sets out to check, and
the original suite never tried feeding the pipeline malformed input —
only well-formed fixtures. A subsequent, deliberate adversarial pass —
attacking the pipeline with wrong-typed values, `NaN`, negative amounts,
and a string in place of a `date` object — found four real problems, all
fixed by adding `src/validation.py` as Step 0 of the orchestrator:

1. **A negative amount completed silently**, as if it were an ordinary,
   valid small purchase.
2. **`float('nan')` as an amount also completed silently** — the more
   serious of the four, since Python's `NaN` comparisons are always
   `False`, so a nonsensical amount fell through every check as if it had
   been properly compared against the configured limit and found
   acceptable. A confident, wrong "this is fine" answer is a worse
   failure mode than a crash.
3. **A string-typed amount, or a string in place of a real date object,
   crashed the pipeline outright** with an unhandled `TypeError`.
4. **A missing (`None`) category was silently treated as a legitimate
   "unconfigured category"** rather than being recognized as input that
   isn't a valid category at all.

### Round 2: a second review pass

Passing an adversarial test suite is not the same claim as "this code is
correct" — it only proves the specific things that pass was aimed at
checking. A subsequent review pass, looking specifically for gaps the
adversarial pass wasn't aimed at (rather than more malformed-input
variations), found one problem serious enough to call a genuine
correctness defect, plus several smaller documentation and testing gaps:

5. **The pipeline never verified that an agent actually belonged to the
   consumer it claimed to be transacting for.** `registration.py` knew
   which consumer an agent was really registered to; nothing compared
   that against the `consumer_id` the caller supplied. An agent
   registered to one consumer could be used to attempt a transaction "on
   behalf of" a completely different, unrelated consumer — the pipeline
   would see only an empty permissions lookup and treat it as an
   ordinary unconfigured category, indistinguishable from a legitimate
   new-category case. Confirmed directly against the live pipeline
   before the fix: the transaction *completed*, generating a Verifiable
   Intent record that falsely attributed authorization to a consumer who
   had nothing to do with the agent at all. This is the most significant
   finding in this repository's history and is fixed by DD009 (Step 1b,
   `agent_consumer_mismatch`).
6. **`datetime.datetime` passed the original date-validation check** —
   because `datetime.datetime` is a *subclass* of `datetime.date` in
   Python, `isinstance(transaction_date, date)` alone let a full datetime
   object through as "valid," which then crashed downstream when compared
   against a plain `date` with `<=`. The Round 1 fix for a string-typed
   date hadn't closed this adjacent path. Fixed by explicitly rejecting
   `datetime` instances before the general date check runs.
7. Whitespace-only strings (`" "`) passed the original non-empty-string
   check, since `"   " != ""`. Fixed by comparing against `.strip() == ""`
   instead.
8. A transaction that violates both the spending limit and the active
   timeframe at once had a real, deterministic outcome in the code
   (`OUTSIDE_TIMEFRAME` wins, because that check runs first) — but nothing
   tested this, and nothing documented it as a deliberate choice rather
   than an accident of write order. Now tested and named (DD010).
9. `MERCHANT_CATALOG` in `mock_data.py` was dead code — defined, never
   referenced by any actual check — which risked implying that merchant/
   category consistency was validated somewhere. It wasn't, so it was
   removed rather than kept with a disclaimer (DD011).
10. An explicit `"agent-unknown-99": None` entry in the mock registered-
    agent directory was functionally redundant with a plain missing key
    (both produce identical behavior via `.get()`); it and the test that
    only exercised it were removed (DD011).
11. `docs/DESIGN_DECISIONS.md`'s original explanation of why only
    unconfigured categories route to the Authorization Gate overstated
    its own sourcing — it read as if that split followed from
    Mastercard's disclosure, when it is this repository's own
    architectural choice. Reworded in DD003 to say so plainly.

All eleven findings across both rounds are fixed and covered by
regression tests (a third round, below, added two more). The two rounds are recorded separately here
deliberately: a clean adversarial-testing pass is evidence about
malformed input specifically, not a general certificate of correctness,
and this repository does not want to overstate what Round 1 alone
established.

### Round 3: a third review pass, asking one question of every branch

A third pass asked of each branch: **what else could arrive here looking
exactly like this?** The first two rounds' most serious findings (NaN and
negative amounts passing as within-limit, a stranger's account and a `None`
category passing as a new category) were all answers to that question. Asked
once more, it found one more:

12. **A configured category written differently bypassed its restriction.**
    The lookup was an exact match on the label the agent supplies, so
    `Household_Staples` missed Devon's configured `household_staples` entry,
    came back UNCONFIGURED, and went to the Gate. Confirmed before the fix:
    Devon's groceries, $70, dated after Devon's active window, escalated as
    `household_staples` and **completed** as `Household_Staples`. Fixed by
    comparing categories in one canonical spelling (DD012).
13. Fixing #12 surfaced an adjacent case: a category made only of
    separators (`"-"`) passed the non-empty check and would have normalised
    to an empty label. It is now rejected as malformed.

Both are fixed and covered by regression tests. The fix stops where the public
record stops: synonyms (`groceries` for `household_staples`) are not mapped
(see "Known limitations").

## Known limitations

- **The category is a label the agent asserts, not one this pipeline
  verifies.** Spelling variants are normalised (DD012), but a *different*
  label for the same kind of purchase (`groceries` for a configured
  `household_staples`) is treated as a category the consumer never
  configured and goes to the Authorization Gate, where the consumer's
  configured limit and window for `household_staples` do not apply.
  Closing that would need a category taxonomy or merchant-to-category
  mapping, and Mastercard has disclosed neither; this repository does not
  invent one. A deployment would need the Gate's decision function, or a
  category source it trusts, to account for this.

- **No real cryptography anywhere.** Registration/verification and the
  Verifiable Intent record are both mocked as plain Python values, not
  implementations of Web Bot Auth or any real signing scheme. See
  `docs/DESIGN_DECISIONS.md`, Decision 005.
- **Mock data only.** Three registered-agent entries across two separate
  consumers, two consumer/agent permission configurations, three
  merchants. This models a small number of consumers' transaction paths
  through the pipeline, not throughput, concurrency, or Mastercard's
  actual scale.
- **The `merchant` field is accepted but not itself checked against any
  consumer-configured restriction.** It flows through to the Gate context
  and the Verifiable Intent record, but this pipeline validates category,
  spending limit, and an active date window only — merchant-level and
  usage-rule-level restriction, both confirmed dimensions in Mastercard's
  own language, are not modeled here. See `docs/DESIGN_DECISIONS.md`,
  Decision 011.
- **No connection to Decision Intelligence Pro's fraud scoring.** This
  pipeline models Agent Pay's confirmed registration/permission/intent
  functions only. No Mastercard source connects DI Pro's fraud-scoring
  pipeline to Agent Pay's authorization flow, and this repository does not
  construct that connection.
- **The permission schema (category, spending limit, timeframe, usage
  rule) is one illustrative realization of Mastercard's confirmed
  restriction dimensions, not a disclosed schema.** A real system may
  structure these differently, combine them differently, or support
  dimensions this repository does not model.
- **None of the three review passes was exhaustive.** The first two found and
  closed eleven real issues, and the third found two more (#12–13) (see
  "What building it surfaced"), which demonstrates that looking for
  problems beyond the original test suite mattered — twice — not that no
  further defects remain. Unicode edge cases, extremely long string
  fields, calendrically invalid-but-correctly-typed dates (e.g., a real
  `date` object constructed from bad arithmetic elsewhere in a caller's
  code), and concurrent/overlapping transactions for the same agent were
  not specifically probed by either pass.
- **The Gate's demo policy (`demo.py`) has no relationship to any real
  Mastercard authorization rule.** It exists solely so the pipeline is
  runnable end to end, and is explicitly not labeled as a legitimate
  illustrative default the way this repository's other constructed values
  are. See `docs/DESIGN_DECISIONS.md`, Decision 004.

## Explicit non-claims

This repository is **not** a disclosure of Mastercard's actual Agent Pay
system, Decision Intelligence Pro, or Verifiable Intent implementation. It
does not claim Mastercard's real system works this way, uses this
permission schema, this registration mechanism, or any particular
authorization rule for unconfigured categories, and it should not be cited
as evidence of Mastercard's technical architecture. It is an illustrative,
tested scaffold, built entirely from Mastercard's own public statements
and reporting quoting Mastercard executives on the record, constructed to
be consistent with — and no richer than — what that public record actually
supports. Every place this repository goes beyond a directly confirmed
function is labeled as construction, and the Authorization Gate's total
absence of default criteria is the clearest expression of where Mastercard's
public disclosure actually stops.

## Running it

```bash
# From the repository root, with Python 3.10+ (uses the `X | Y` union
# type syntax and dataclasses):

# Run the full test suite
python3 -m unittest discover -s tests -v

# Run the demo (exercises every terminal outcome at least once)
python3 demo.py
```

No external services, API keys, or network access are required or used
anywhere in this repository.
