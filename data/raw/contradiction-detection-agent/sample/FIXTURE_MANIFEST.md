# Fixture manifest: contradiction-detection-agent sample corpus

Machine view: `fixture-manifest.json` (SHA-256 of every file; step 1 refuses to run if one changes).

**Everything here is invented.** The companies are fictional (`FXA`…`FXQ`, names ending "Fixture Co").
No real company, filing, earnings call or article is represented. Row shapes follow the original
workflow's SQL `SELECT` lists, so each file stands for "what that fetch would return".

Frozen clock: `2026-09-30T00:00:00+00:00`. Expected detector output for the clean set: `expected-flags.json`,
written before any code and checked against the original JavaScript by the parity check.

## Clean set

| Company | What it tests |
|---|---|
| `FXA` | P1 fires: weakened guidance (conf 0.80 ≥ 0.6) against POSITIVE news (avg 0.40 > 0.2) |
| `FXB` | P1 near-miss: weakened guidance at conf 0.55 (< 0.6) does not fire despite POSITIVE news |
| `FXC` | One 'strengthened guidance vs negative news' situation fires both P1 (branch 2) and P6 → two HIGH flags → CRITICALLY_COMPROMISED |
| `FXD` | P6 near-miss: same picture as FXC but only 4 articles (< 5), so P6 is silent; P1 branch 2 still fires |
| `FXE` | P2 tone: high-severity risk with matching POSITIVE coverage → HIGH; no tech data → P4/P5 skipped |
| `FXF` | Tags are matched as text: risk 'supply chain' and news tag 'supply_chain' don't match → coverage-gap MEDIUM; a critical risk with matching NEGATIVE coverage raises nothing (near-miss) |
| `FXG` | P3 counts topics that were repeated or scored pressure ≥ 7: 'capex' was asked repeatedly and 'pricing' scored 8, both answered directly; P3 counts both (its wording says 'evaded') |
| `FXH` | P3 near-miss: only one topic qualifies (needs ≥ 2), despite positive analyst news |
| `FXJ` | P4 fires: 2 declining languages against strengthened guidance (conf 0.65 ≥ 0.6) |
| `FXK` | P4 near-miss: 1 declining language and 4 stale repos (thresholds are 2 and 5) |
| `FXL` | P5 fires: engineering burst (z 2.4) with no strengthened or pivot-worded guidance |
| `FXM` | Same burst as FXL, but guidance topic 'contract renewals' contains 'new', which the keyword match counts as a pivot disclosure, so P5 stays silent |
| `FXN` | Quiet company with no tech data: nothing fires; P4/P5 recorded as skipped, not as passed |
| `FXP` | Two MEDIUM flags (P2 gap + P3) and no HIGH → REVIEW_WARRANTED |
| `FXQ` | Port-fidelity case: news average is exactly 0.625, a rounding tie (JS toFixed → '0.63', Python's default → '0.62'), and confidence 1.0 (JS prints '1', Python '1.0') |
| `FXR` | Boundary case: weakened guidance at confidence exactly 0.60 fires, because the test is >= 0.6 (a port using > or 0.61 fails here) |

## Defective set

| ID | Source | Row | Field | Defect | Must be caught by |
|---|---|---|---|---|---|
| D01 | guidance-signals | `G-FXA-1` | direction | the direction the detector reads is absent | step 3: missing_required |
| D02 | guidance-signals | `G-FXC-1` | direction_confidence | confidence sent as text, which JavaScript would quietly coerce to a number | step 3: type_error |
| D03 | guidance-signals | `G-FXD-1` | direction | 'up' is not one of strengthened / weakened / unchanged | step 3: not_in_allowed_set |
| D04 | guidance-signals | `G-FXJ-1` | direction_confidence | a confidence above 1 | step 3: out_of_bounds |
| D05 | guidance-signals | `G-FXN-1` | call_date | a call 2.7 years old, outside the declared 365-day lookback (the original queries select without a date filter) | step 4: reported and KEPT, as the original keeps it |
| D06 | guidance-signals | `(appended string)` | — | a bare string where a row object belongs | step 3: row_not_object |
| D07 | risk-admissions | `R-FXE-1` | severity | 'severe' is not one of low / medium / high / critical | step 3: not_in_allowed_set |
| D08 | risk-admissions | `R-FXP-1` | schema_valid | the validity marker the queries filter on is absent | step 3: missing_required |
| D09 | risk-admissions | `R-FXF-1` | — | the same row delivered twice | step 4: later copy withheld, listed |
| D10 | news-signals | `N-FXA-2` | sentiment_score | score as text, which JavaScript would add into the average as a string | step 3: type_error |
| D11 | news-signals | `N-FXG-1` | topic_tags | tags as one string instead of a list | step 3: type_error |
| D12 | news-signals | `N-FXC-3` | published_at | not a timestamp | step 3: type_error |
| D13 | news-signals | `N-FXB-1` | schema_valid | a row marked invalid that a query would never return | step 4: withheld: schema_valid is not true |
| D14 | news-signals | `N-ZZZZ-1` | ticker | a company no run declared | step 4: withheld: outside the declared companies |
| D15 | tech-stack-signals | `T-FXL-1` | declining_languages | null list, which the JavaScript treats as an empty list | step 3: missing_required |
| D16 | tech-stack-signals | `T-FXJ-1` | burst_detected | boolean as text; the JavaScript accepts 'true', while the data contract asks for a boolean | step 3: type_error |
| D17 | qa-pressure-map | `qa-pressure-map.json.broken` | — | the whole Q&A source is truncated mid-object | step 3: reported; the source contributes no rows |

## Not covered

- live database or API behaviour (timeouts, 401/403/429, empty pages)
- the LLM's responses (never called)
- concurrency or reruns against a real upsert
