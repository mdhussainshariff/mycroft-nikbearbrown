# Audit: contradiction-detection-agent, run `sample-001-defective`

> What this run found, step by step. It reports; it does not approve. Approval is a gate decision by a named human.

- Mode: **sample** · fixture set: **defective** · frozen clock: `2026-09-30T00:00:00+00:00`
- Corpus: synthetic, fictional companies (see `data/raw/contradiction-detection-agent/sample/FIXTURE_MANIFEST.md`)
- Live calls made: **none** · network access: **none**

## Records in, records out

| Step | In | Out | Withheld / findings |
|---|---|---|---|
| 2 ingest | 5 sources | 65 rows | 1 source(s) unparseable, carried as-is |
| 3 shape: guidance-signals | 12 | 7 | 5 row finding(s), 0 parse error(s) |
| 3 shape: risk-admissions | 7 | 5 | 2 row finding(s), 0 parse error(s) |
| 3 shape: qa-pressure-map | — | — | 0 row finding(s), 1 parse error(s) |
| 3 shape: news-signals | 32 | 29 | 3 row finding(s), 0 parse error(s) |
| 3 shape: tech-stack-signals | 14 | 12 | 2 row finding(s), 0 parse error(s) |

## What was withheld, and why

- **qa-pressure-map**: unparseable source. does not parse: Invalid control character at: line 85 column 21 (char 2403)
- **guidance-signals** row `G-FXA-1` (index 0): missing_required on `direction`
- **guidance-signals** row `G-FXC-1` (index 2): type_error on `direction_confidence`
- **guidance-signals** row `G-FXD-1` (index 3): not_in_allowed_set on `direction`
- **guidance-signals** row `G-FXJ-1` (index 4): out_of_bounds on `direction_confidence`
- **guidance-signals** row (not an object) (index 11): row_not_object
- **risk-admissions** row `R-FXE-1` (index 1): not_in_allowed_set on `severity`
- **risk-admissions** row `R-FXP-1` (index 5): missing_required on `schema_valid`
- **news-signals** row `N-FXA-2` (index 1): type_error on `sentiment_score`
- **news-signals** row `N-FXC-3` (index 6): type_error on `published_at`
- **news-signals** row `N-FXG-1` (index 19): type_error on `topic_tags`
- **tech-stack-signals** row `T-FXJ-1` (index 7): type_error on `burst_detected`
- **tech-stack-signals** row `T-FXL-1` (index 9): missing_required on `declining_languages`

## Kept, but worth a human look

Not checked: step 4 (quality) did not run, so duplicates and rows older than the lookback were not looked for.

## Catalogued defects in this corpus

The manifest catalogues 17 defects: 13 for step 3 (shape) and 4 for step 4 (quality). This run stopped at step 3, so the step-4 defects were not reached here. The self-test checks every one mechanically, running step 4 on its own where needed (logs/contradiction-detection-agent/self-test-results.json).
