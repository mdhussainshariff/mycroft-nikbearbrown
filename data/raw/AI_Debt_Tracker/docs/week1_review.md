# Week 1 review — what was checked before the freeze

> **Who did what.** This review was carried out by Claude (an AI model), so everything below is a
> **model judgment** (P8). Om Mali, who has no financial background, asked for the review and
> accepted it as the basis for clearing the Week 1 gate on 2026-10-18. Om did not check the filings
> personally. The gate record is `manifests/week1_gate.json`. Anyone may re-open the gate by
> checking the rows below themselves (P7).

## What the gate covers

| Item | Decision | Evidence |
|---|---|---|
| AI universe (25 companies) and each company's grading level | **Frozen** with 2 overrides (Meta → L2, TeraWulf → L1) | [`universe_v1_review.md`](universe_v1_review.md) |
| Generalisation set (75 non-AI companies) | **Frozen** as selected by the rule | `manifests/generalisation.csv` |
| Dev and test episodes (95 + 400) | **Frozen** — built mechanically from the two lists above | `manifests/dev.csv`, `manifests/test.csv` |
| Bake-off set (29 announcements) | **Accepted**, with 7 truth corrections on 6 rows | [`bakeoff_set.md`](bakeoff_set.md), `manifests/bakeoff_truth_corrections.json` |
| Model choice | **`qwen3:4b`** | [`bakeoff.md`](bakeoff.md) |

## Attestation

- Recipe: AI Debt Tracker, Week 1 (`DESIGN.md` §11)
- Review by: Claude (model judgment) · 2026-10-18 · accepted by Om Mali · 2026-10-18

### Tested

| Ran | Saw | Expected |
|---|---|---|
| Read all 29 bake-off passages, plus the opening of each document | All 29 are genuine announcements: 8 final term sheets, 8 prospectus supplements, 13 pricing or closing 8-Ks. None is an earnings release, a debt table or a passing mention. | Every row a real announcement of the instrument listed |
| Compared each row's truth values with what the document itself says | 6 rows disagree with the document: Digital Realty's notes are euros (€850 m), not $941 m (2 rows); two pricing releases state the amount *before* the banks' extra allotment (Core Scientific $400 m, not $460 m; Snowflake $1.0 bn, not $1.15 bn); Oracle's 2028 floating-rate note has a spread (SOFR + 0.76%), not a 0.76% coupon; one Digital Realty 8-K states no amount. All corrected, with reasons. | Truth matches the document |
| Re-scored the bake-off with the corrections | `qwen3:4b` 141/143 fields = 99%, 29/29 valid JSON, slowest 12.6 s; `llama3.1:8b` 91%; `qwen3:8b` 88%. Same order as before the corrections (95 / 88 / 84%). 4 of `qwen3:4b`'s 6 "wrong" amounts were truth errors. | A clear winner that meets the pre-set rule |
| Looked inside the tagged debt of 14 companies whose level was surprising or changed: Microsoft, Alphabet, Meta, Oracle, Intel, Broadcom, Dell, Equinix, Digital Realty, CoreWeave, TeraWulf, Vistra, Constellation, IBM | Each level matches what the company's own tagging shows. Microsoft's members are issuance groups; Oracle and Intel itemise only in annual reports; IBM tags maturity-year buckets; Dell ("Senior Notes" $24 bn) and Vistra ("Vistra Operations Debt" $18 bn) tag lumps, not bonds. | Level = the finest detail the reports really give |
| Re-examined the two 4–4 ties | Meta: 5 offerings cover 100% of its debt whenever it tags them, so L2 fits better than L3. TeraWulf: every report since its first bond (Sep 2025) itemises 100%, so L1 fits better. Overridden, with reasons. | Ties resolved on substance, not by default |
| Scanned the 75 generalisation companies' names and industry codes | No banks, insurers, REITs or AI companies. Two payment companies (Fiserv, Mastercard) are classed as services and issue ordinary corporate bonds, so they stay. | Non-financial, non-AI, tagging per bond |
| Tried to break the split builder: same-quarter start/target, missing EDGAR entries | 0 episodes dropped; every cut-off comes from EDGAR's own index. | No silent drops |

### Did not test

- No 10-Q or 10-K was opened as a document to compare the answer key with its printed debt table. That hand-check of 10 company-quarters is a Week 2 task (`docs/answer_key_week1.md` has the checklist).
- Whether every bond a document announces is in its truth list. Three rows leave one out (Oracle's 5.375% 2054 notes ×2, Equinix's 3.625% 2034 notes); these are unscored, so they change no score.
- Redemption notices and credit agreements: the dev window gave almost none, so the model choice rests on new-bond announcements.
- `qwen3:8b` with thinking mode on, and any prompt other than the one used.
- Whether 29 documents from 12 companies are representative. The win is large (99% vs 88–91%), but the sample is small.

### Broke during testing, fixed

- The first `qwen3:8b` run looped for 10 minutes on one document. An output cap (2,048 tokens) now ends any runaway, and the answer is scored as wrong.
- The level rule first counted members and called Oracle's partial 10-Qs per-bond. It now measures coverage of total debt (P23).
