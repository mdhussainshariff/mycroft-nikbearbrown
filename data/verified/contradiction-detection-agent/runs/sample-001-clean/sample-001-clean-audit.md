# Audit: contradiction-detection-agent, run `sample-001-clean`

> What this run found, step by step. It reports; it does not approve. Approval is a gate decision by a named human.

- Mode: **sample** · fixture set: **clean** · frozen clock: `2026-09-30T00:00:00+00:00`
- Corpus: synthetic, fictional companies (see `data/raw/contradiction-detection-agent/sample/FIXTURE_MANIFEST.md`)
- Live calls made: **none** · network access: **none**

## Records in, records out

| Step | In | Out | Withheld / findings |
|---|---|---|---|
| 2 ingest | 5 sources | 71 rows | 0 source(s) unparseable, carried as-is |
| 3 shape: guidance-signals | 11 | 11 | 0 row finding(s), 0 parse error(s) |
| 3 shape: risk-admissions | 6 | 6 | 0 row finding(s), 0 parse error(s) |
| 3 shape: qa-pressure-map | 9 | 9 | 0 row finding(s), 0 parse error(s) |
| 3 shape: news-signals | 31 | 31 | 0 row finding(s), 0 parse error(s) |
| 3 shape: tech-stack-signals | 14 | 14 | 0 row finding(s), 0 parse error(s) |
| 4 quality | — | 71 | 0 duplicate(s), 0 reject(s), 0 stale row(s) kept |
| 5 detection | 16 companies | 13 flag(s) | LLM review prepared, not sent |

## What was withheld, and why

Nothing was withheld.

## Kept, but worth a human look

Nothing.

## Expected versus actual (clean corpus)

| Company | Expected flags | Actual flags | Same flags and level |
|---|---|---|---|
| FXA | 1 | 1 | yes |
| FXB | 0 | 0 | yes |
| FXC | 2 | 2 | yes |
| FXD | 1 | 1 | yes |
| FXE | 1 | 1 | yes |
| FXF | 1 | 1 | yes |
| FXG | 1 | 1 | yes |
| FXH | 0 | 0 | yes |
| FXJ | 1 | 1 | yes |
| FXK | 0 | 0 | yes |
| FXL | 1 | 1 | yes |
| FXM | 0 | 0 | yes |
| FXN | 0 | 0 | yes |
| FXP | 2 | 2 | yes |
| FXQ | 1 | 1 | yes |
| FXR | 1 | 1 | yes |
