# Design Decisions

This log exists so that decisions made while building this repository are
recorded and traceable, not quietly resolved and forgotten. It follows the
same convention every prior entry in this series has used.

---

**DD001 — Registration failures are rejected outright, not escalated to the consumer.**
Mastercard's own language treats agent registration and verification as a
network-level precondition for transacting at all, not a per-transaction
decision the consumer makes case by case. This repository's orchestrator
therefore returns `REJECTED` for an unregistered or unverified agent and
never touches the permission check or the Gate for that transaction. This
mirrors the "rejected outright — not escalated" distinction drawn explicitly
in Section 4 of the case study.

**DD002 — `OUTSIDE_LIMIT` and `OUTSIDE_TIMEFRAME` are kept as two separate
reasons, not merged into one "policy violation" reason.**
Both are unambiguous violations of something the consumer actively
configured, but they are different findings about the world: one says the
amount is wrong for an otherwise-valid window, the other says the timing is
wrong for an otherwise-valid amount. Collapsing them would lose information
a real consumer reviewing an escalated transaction would want.

**DD003 — Only `UNCONFIGURED` routes to the Authorization Gate; `OUTSIDE_LIMIT`
and `OUTSIDE_TIMEFRAME` do not.**
This is the central structural decision in this repository. **It is worth
being precise about how it is sourced, because an earlier version of this
document overstated that: this specific split — some violations escalate
by a deterministic rule, only one kind routes to an external decision
function — is this repository's own architectural choice, not something
Mastercard's public language distinguishes one way or the other.** Mastercard
confirms that consumers can restrict Agentic Tokens by category, merchant,
spending limit, timeframe, and usage rule; it does not say anything about
*how* a violation of one of those restrictions gets handled operationally,
let alone that some violations are unambiguous while others require a
decision. The reasoning behind choosing this split anyway: an amount
exceeding an actively-set limit, or a date outside an actively-set window,
is a violation of something the consumer explicitly configured — there is
nothing to decide, only something to compare. A category the consumer never
configured at all has no instruction to check against, which is a
genuinely different, harder problem. This repository treats that second
case, and only that case, as the one requiring an external decision — but
readers should treat this as a design choice this case study made to give
the Gate a well-defined scope, not as an inference read out of Mastercard's
own disclosure. (Caught during a second review pass — see Finding #4.)

**DD004 — The Gate ships with zero default authorization criteria, under
any label.**
Every other undisclosed mechanism in this pipeline (the mock registration
directory, the permission schema, the Verifiable Intent record's fields)
received an explicitly labeled, illustrative construction. The Gate did
not, on purpose. Mastercard confirms that agents transact within
consumer-set permissions and limits — a category, not a boundary for what
should happen in a case the consumer never anticipated. Inventing a
labeled placeholder rule here ("[DEV] auto-approve unconfigured categories
under $50") would have implied a shape of answer that nothing in the
public record supports. The demo's `example_gate_policy` in `demo.py`
exists only so the pipeline is runnable end to end, is explicitly NOT
marked `[DEV]`, and is logged as a named exception to this repository's own
labeling convention — the same treatment this series gave to Lemonade's
flat-threshold demo policy and Zurich's demo decision function.

**DD005 — Registration/verification and the Verifiable Intent record are
both deliberately non-cryptographic.**
Real Web Bot Auth verification is a cryptographic signature check; a real
Verifiable Intent record is described by Mastercard as tamper-resistant and
cryptographically provable. This repository implements neither as
cryptography — both are plain booleans and a plain dict, respectively.
Simulating real cryptographic behavior would imply a level of fidelity to
Mastercard's actual mechanism that nothing in the public record supports,
since Mastercard has not disclosed the signing scheme, key management, or
storage architecture for either.

**DD006 — `unregistered_agent` and `unverified_agent` are two distinct
reasons, not one `registration_failed` reason.**
Mastercard's own language names registration and verification as two
separate steps ("registered AND verified"). An agent that is registered
but currently failing verification (mock agent `agent-concierge-02`) is a
meaningfully different state from an agent the network has never seen at
all — the first suggests something is wrong with an existing credential;
the second suggests the agent was never onboarded in the first place.

**DD007 — Input validation was added after an adversarial testing pass,
not designed in from the start.**
The original build (45 tests) passed cleanly on its first complete run.
That was accurate, but narrower than it read: the original test suite
never tried feeding the pipeline malformed input, only well-formed
fixtures. A deliberate adversarial pass — attacking the pipeline with
wrong-typed values, NaN, negative amounts, and a string date instead of a
`date` object — found two silent wrong-answer bugs (a negative amount and
a NaN amount both completed as if they were valid, ordinary transactions)
and two unhandled crashes (a string amount, a string date). All four are
now fixed by `validation.py`, running as Step 0 of the orchestrator,
before the registration check. `malformed_transaction_input` and
`invalid_transaction_date` are kept as two distinct reasons rather than
one generic reason, for the same reason DD002 keeps `OUTSIDE_LIMIT` and
`OUTSIDE_TIMEFRAME` separate: "the date can't be read" is a different
claim than "the rest of the input is unusable." This finding, and the
narrative update it required in Section 4 of the case study, are recorded
in Section 6 as a matter of record rather than quietly patched into the
code while the published workflow stayed silent about it.

**DD008 — A `None` category is treated as malformed input, not as an
`UNCONFIGURED` category.**
Before DD007's fix, `category=None` was silently accepted by
`permissions.py`'s dictionary lookup and treated as a category the
consumer simply never configured — because `dict.get(None)` returns
`None` just as cleanly as a genuine cache miss on a real string key. This
conflated two different claims: "this is a real category the consumer
never set a permission for" versus "this input isn't a valid category at
all." `validation.py` now catches the second case before `permissions.py`
ever runs.

**DD009 — Agent-consumer ownership is checked immediately after registration,
before permissions.py ever runs (added after a second review pass, Finding #1).**
The original build checked that an agent was registered and verified, but
never checked that the agent actually belonged to the consumer_id the
caller claimed it was acting for. Before this fix, an agent genuinely
registered to one consumer could be used to attempt a transaction "on
behalf of" a different, unrelated consumer_id — the pipeline would see an
empty permissions lookup for that (consumer, agent) pair and treat it as an
ordinary `UNCONFIGURED` category, indistinguishable from a legitimate new
category, and route it to the Gate with no signal that anything was
actually wrong. If the Gate's supplied decision function happened to
approve it — which every gate policy used elsewhere in this repository's
own demo and tests does, by default, for a plausible-looking small amount —
the transaction completed and a Verifiable Intent record was created
falsely attributing authorization to the wrong consumer. This is now
checked as its own step (`agent_consumer_mismatch`), rejected outright at
the same stage as any other registration-level failure, before
permissions.py or the Gate are ever touched. `mock_data.py` was extended
with a second, real consumer (`morgan-02`) and agent (`agent-concierge-03`)
specifically so this could be tested against a genuine ownership mismatch,
rather than only a claim against an arbitrary string.

**DD010 — When a transaction violates both the spending limit and the
active timeframe simultaneously, `OUTSIDE_TIMEFRAME` wins, deterministically
(added after a second review pass, Finding #6).**
This was already true of the code (the timeframe check runs before the
limit check in `permissions.py`), but it was neither tested nor named as a
deliberate choice — an oversight in the same category as the ordering
question this series' Zurich entry caught and named explicitly for its
own contradiction-vs-missing-policy check. There is no strong reason,
grounded in anything Mastercard discloses, to prefer one order over the
other; this repository simply fixes one and now tests it, rather than
leaving the actual behavior for a combined failure undocumented and
untested. A test now proves this ordering holds for a transaction
engineered to fail both checks at once.

**DD011 — `MERCHANT_CATALOG` (dead code) and the explicit
`"agent-unknown-99": None` entry (functionally redundant) were both removed
during a second review pass (Findings #7 and #8).**
`MERCHANT_CATALOG` was defined in `mock_data.py` but never referenced by
any check anywhere in the pipeline — the `merchant` field is accepted as
input and flows through to the Gate context and the intent record, but is
not itself validated against any consumer-configured restriction (see
README.md, "Known limitations"). Leaving an unused merchant/category
mapping in the mock data risked implying that consistency between the two
is checked somewhere; it wasn't, so the dead code was removed rather than
kept with a disclaimer. Separately, `"agent-unknown-99": None` in
`REGISTERED_AGENTS` produced identical behavior to a totally absent
dictionary key (both return `None` from `.get()`), so it added
documentation value but no test coverage beyond what
`test_unknown_agent_id_fails_as_unregistered` already provides against a
plain missing key. It was removed, and the corresponding test that only
exercised it was removed with it.


**DD012 — Category labels are compared in a canonical spelling; synonyms are
deliberately not mapped (added after a third review pass).**
The permission lookup was an exact string match on a category label the
agent itself supplies. A third review pass, asking of each branch "what
else could arrive here looking exactly like this?", found that a
*configured* category written differently looked exactly like a category
the consumer never configured. Confirmed against the live pipeline before
the fix: Devon's groceries, $70, dated after Devon's active window,
ESCALATED as `household_staples` (`outside_timeframe`) but COMPLETED
through the Authorization Gate as `Household_Staples`, `household_staples `
or `household-staples`. A restriction Devon actively set was bypassed by
spelling alone, which also contradicted DD003's premise that a violation of
an actively-set limit or window always escalates. `permissions.normalise_category`
now puts the incoming label *and* the configured keys into one canonical
form (surrounding whitespace removed, letter case folded, runs of spaces,
hyphens and underscores joined by a single underscore), once, in the
orchestrator before Step 2, so the permission check, the Gate context and
the Verifiable Intent record all see the same category. Fixing it surfaced
an adjacent case: a category made only of separators (`"-"`, `"___"`)
passed the non-empty check and would normalise to `""`. It is now rejected
in `validation.py` as `malformed_transaction_input`.
**Scope, stated as deliberately as DD004's:** this normalises spelling, not
meaning. `groceries` is still a different label from `household_staples`
and still routes to the Gate as unconfigured. Deciding which labels are
synonyms, or deriving a category from the merchant, would mean inventing a
category taxonomy Mastercard has not disclosed. The category therefore
remains a label the agent asserts, not one this pipeline verifies (README,
"Known limitations"), and a test pins that boundary rather than hiding it.
