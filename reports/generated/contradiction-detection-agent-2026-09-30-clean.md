# Contradiction detection: sample run `sample-001-clean`

**Reader:** the domain lead who decides whether this run moves forward.  
**Decision enabled:** approve the run for the next phase, request source or schema fixes, or block live execution.

## Run summary

- 16 fictional companies checked, 13 disagreement flag(s) raised, every one routed to a human.
- Mode **sample**: no database, API or model was contacted.

## Purpose

Find places where a company's own statements and the outside signals about it disagree (earnings guidance, risk admissions, analyst Q&A, news sentiment, engineering activity), and hand each disagreement to a human. The detector surfaces conflict; it does not resolve it, and it never recommends buying or selling.

## Source inventory

| Source | Stands for (original node) | Rows | Parsed |
|---|---|---|---|
| guidance-signals | DB: Fetch Earnings Guidance Signals | 11 | yes |
| risk-admissions | DB: Fetch Risk Admissions | 6 | yes |
| qa-pressure-map | DB: Fetch QA Pressure Map | 9 | yes |
| news-signals | DB: Fetch News Signals | 31 | yes |
| tech-stack-signals | DB: Fetch Tech Stack Signals | 14 | yes |

## Inputs used

- Run envelope: `data/raw/contradiction-detection-agent/run-envelope.json` (`run_id` sample-001, lookback 365 days, patterns [1, 2, 3, 4, 5, 6])
- Fixture set `clean` under `data/raw/contradiction-detection-agent/sample/clean/`
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
- 3. validate-data-shape: completed
- 4. transform-quality-check: completed
- 5. run-approved-tools: completed

## Records seen

71 rows across 5 sources (details in the audit).

## Rejects

0 (shape findings 0, unparseable sources 0, quality rejects 0). Each is listed with its reason in the audit and the agent log.

## Duplicates

0 (the later copy withheld in each case).

## Flags

| Company | Pattern | Severity | What disagrees | Reading note |
|---|---|---|---|---|
| FXA | 1. Sentiment vs Guidance Direction | HIGH | Guidance for "cloud margin" marked WEAKENED but news sentiment is POSITIVE |  |
| FXC | 1. Sentiment vs Guidance Direction | HIGH | Guidance STRENGTHENED on call but news sentiment is NEGATIVE |  |
| FXC | 6. Guidance Optimism vs Negative News Momentum | HIGH | Management projects high-confidence strengthened guidance against sustained negative news momentum | The same guidance claim also raised a Pattern 1 flag, so these two flags describe one disagreement. |
| FXD | 1. Sentiment vs Guidance Direction | HIGH | Guidance STRENGTHENED on call but news sentiment is NEGATIVE |  |
| FXE | 2. Risk Admission vs Coverage Tone | HIGH | High-severity risk "regulation" admitted on call; matching news has POSITIVE sentiment |  |
| FXF | 2. Risk Admission vs News Coverage Gap | MEDIUM | High-severity risk "supply chain" admitted on call but absent from news coverage | News is matched to a risk by comparing tag text, so the same topic written differently (with a space instead of an underscore, say) doesn't match. Worth checking the coverage by hand. |
| FXG | 3. QA Evasion vs Analyst Confidence | MEDIUM | Management evaded 2 high-pressure Q&A topics but analyst coverage is positive | This pattern's input is a repeated topic or a pressure score of 7 or more, so 'evaded' reads best as 'asked repeatedly or under pressure'. |
| FXJ | 4. Tech Stack Decline vs Positive Guidance | HIGH | Management projects strengthened guidance but engineering footprint shows decline |  |
| FXL | 5. Engineering Burst vs Undisclosed Pivot | HIGH | Significant engineering burst detected but no corresponding management disclosure on earnings call |  |
| FXP | 2. Risk Admission vs News Coverage Gap | MEDIUM | High-severity risk "cybersecurity" admitted on call but absent from news coverage | News is matched to a risk by comparing tag text, so the same topic written differently (with a space instead of an underscore, say) doesn't match. Worth checking the coverage by hand. |
| FXP | 3. QA Evasion vs Analyst Confidence | MEDIUM | Management evaded 2 high-pressure Q&A topics but analyst coverage is positive | This pattern's input is a repeated topic or a pressure score of 7 or more, so 'evaded' reads best as 'asked repeatedly or under pressure'. |
| FXQ | 1. Sentiment vs Guidance Direction | HIGH | Guidance for "unit volumes" marked WEAKENED but news sentiment is POSITIVE |  |
| FXR | 1. Sentiment vs Guidance Direction | HIGH | Guidance for "subscription margin" marked WEAKENED but news sentiment is POSITIVE |  |

## Typed TODOs

None open.

## Human approvals

Recorded gate decisions are listed above. Nothing in this run was approved by a machine.

## Verified findings

- Each flag is a **detected disagreement between two named sources**, computed by the ported detector, whose output matches the original workflow's JavaScript on every sample company (parity check).
- No evidence older than the declared lookback was used.

## Inferred findings

None. The optional LLM review (the original's analyst memo, plausibility and relevance scores) was prepared as a handoff and **not sent**; it needs a gate-5 approval naming a human.

## Decision recommendation

All six gates are decided for this sample run; nothing further is pending in sample mode. Live mode is denied (gate 5); reopening it is a separate decision.
