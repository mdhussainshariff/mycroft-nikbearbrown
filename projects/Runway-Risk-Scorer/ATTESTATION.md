# Attestation — Runway-Risk Scorer

**Recipe:** runway-risk-scorer
**Status at attestation:** RUNNABLE-SAMPLE
**Attested by:** Amruta Naik (acting reviewer, SOLO)
**Date:** 2026-09-11

This record states honestly what was tested, what was deliberately not tested, and
what broke and was fixed during the build. It is written to prevent overclaiming:
the reader should assume only what is listed under "Tested," and treat everything
under "Did NOT test" as unverified.

---

## Tested (verified to work)

- **End-to-end sample run.** The recipe runs the full pipeline (ingest → shape-
  validation → score → report) against the schema-matched sample set for all four
  sample companies, exits cleanly, and produces both a human-readable brief and
  machine-readable JSON.
- **The five core metrics** (total raised, months since last raise, funding-stage
  trend, distress-indicator count, signal freshness) compute correctly on the
  sample data, each carrying the signal_id and source_url it was derived from.
- **The two rigor metrics** (trailing-window activity, signal-velocity delta)
  behave as predicted in the pre-registration note: an active company (vela-systems)
  reads positive velocity; a dormant one (lumen-labs, newest signal 2022) reads zero.
- **Provenance rule (P3).** Every emitted number cites a source; missing data is
  reported as UNKNOWN rather than guessed.
- **Validation rule (P2).** Unvalidated signals are dropped, not scored. Confirmed
  via orphan-co, whose single unvalidated signal is excluded (used=0, dropped=1).
- **Human gate (P1/P4).** The recipe halts before any verdict and never labels a
  vendor "safe" or "risky."
- **Break tests (7/7 passing).** The tool fails safely on malformed money strings,
  future dates, empty companies, missing source_urls, unvalidated signals, and
  malformed dates — reporting UNKNOWN or dropping the input rather than crashing.
- **Source-freshness audit.** Runs on the sample set and correctly flags stale
  signals (5 older than 365 days) and unvalidated ones, with 0 hard problems.

## Did NOT test (out of scope / unverified)

- **Live / real-world data.** The recipe has only been run against synthetic
  sample data. It has NOT been run against real companies or a live data source.
  Real-world accuracy is therefore unverified.
- **Correctness of the metric design for real procurement.** Whether these five
  metrics actually predict vendor runway in practice was not evaluated — the tool
  is a first-pass filter, not a validated financial model.
- **Independent review.** All review was performed solo. No second person has
  independently confirmed the outputs, the metric choices, or the adequacy of the
  tests. The "human gate" was cleared by the author acting as reviewer.
- **Scale / performance.** Only run on a handful of sample companies; behaviour on
  large signal sets is untested.
- **Dead-link resolution.** The freshness audit flags stale dates and missing
  source_urls, but does not fetch URLs to confirm they still resolve (sample URLs
  are illustrative, not live).

## Broke and fixed (issues found during the build)

- **Malformed-date crash (found by break tests, fixed).** An early run crashed when
  a signal carried an unparseable date string. The break-test suite caught this. Fix:
  added a `safe_date()` helper that returns None on any malformed date, so bad dates
  are skipped rather than throwing. All date handling was routed through it; the
  break test now passes and the pipeline fails safely on bad dates.

---

## Reviewer's decision

On the evidence above — a clean end-to-end sample run, passing break tests, a
generated audit, and metrics matching pre-registered predictions — the recipe is
marked **RUNNABLE-SAMPLE**. This is the committed ceiling. Advancing to
RUNNABLE-LIVE or VERIFIED would require live data and independent attestation,
which are explicitly out of scope for this phase.

*This tool computed metrics. It did not decide anything.*
