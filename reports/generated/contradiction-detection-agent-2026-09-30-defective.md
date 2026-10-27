# Contradiction detection: sample run `sample-001-defective`

**Reader:** the domain lead who decides whether this run moves forward.  
**Decision enabled:** approve the run for the next phase, request source or schema fixes, or block live execution.

## Run summary

- Detection did not run: the run stopped at validate-data-shape.
- Mode **sample**: no database, API or model was contacted.

## Purpose

Find places where a company's own statements and the outside signals about it disagree (earnings guidance, risk admissions, analyst Q&A, news sentiment, engineering activity), and hand each disagreement to a human. The detector surfaces conflict; it does not resolve it, and it never recommends buying or selling.

## Source inventory

| Source | Stands for (original node) | Rows | Parsed |
|---|---|---|---|
| guidance-signals | DB: Fetch Earnings Guidance Signals | 12 | yes |
| risk-admissions | DB: Fetch Risk Admissions | 7 | yes |
| qa-pressure-map | DB: Fetch QA Pressure Map | None | NO |
| news-signals | DB: Fetch News Signals | 32 | yes |
| tech-stack-signals | DB: Fetch Tech Stack Signals | 14 | yes |

## Inputs used

- Run envelope: `data/raw/contradiction-detection-agent/run-envelope.json` (`run_id` sample-001, lookback 365 days, patterns [1, 2, 3, 4, 5, 6])
- Fixture set `defective` under `data/raw/contradiction-detection-agent/sample/defective/`
- Original workflow: `data/mycroft-main/n8n-workflows/originals/n8n_Workflows/Contradiction_Detection_Agent/Contradiction_detection_agent.json`

## Phase-gate results

| Gate | Decision | By | When |
|---|---|---|---|
| 1. Source gate | approve | Tanmay Kulkarni | 2026-10-04 |
| 2. Scope gate | approve | Tanmay Kulkarni | 2026-10-04 |
| 3. Data-shape gate | approve | Tanmay Kulkarni | 2026-10-04 |
| 4. Script-readiness gate | approve | Tanmay Kulkarni | 2026-10-04 |
| 5. Approval gate | deny | Tanmay Kulkarni | 2026-10-04 |
| 6. Report gate | approve | Tanmay Kulkarni | 2026-10-04 |

## Steps completed

- 1. verify-provenance: completed
- 2. ingest-inputs: completed
- 3. validate-data-shape: STOPPED
- 4. transform-quality-check: not run
- 5. run-approved-tools: not run

## Records seen

65 rows across 5 sources (details in the audit).

## Rejects

13 (shape findings 12, unparseable sources 1, quality rejects not checked: step 4 did not run). Each is listed with its reason in the audit and the agent log.

## Duplicates

Not checked: step 4 (quality) did not run, so duplicates were not looked for.

## Flags

None raised.

## Typed TODOs

None open.

## Human approvals

Recorded gate decisions are listed above. Nothing in this run was approved by a machine.

## Verified findings

- None: detection did not run on this set.
- Not checked: step 4 did not run, so the age of the evidence was not examined.

## Inferred findings

None. The optional LLM review (the original's analyst memo, plausibility and relevance scores) was prepared as a handoff and **not sent**; it needs a gate-5 approval naming a human.

## Decision recommendation

Read the shape findings and fix the sources; detection did not run on this set. Live mode is denied (gate 5); reopening it is a separate decision.
