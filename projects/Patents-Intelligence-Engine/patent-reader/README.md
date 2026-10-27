# Patent Reader

Reads a patent's claims text and citation lineage from real public data, with an optional Claude-based protection-scope classification. Split into a FastAPI backend (`backend/`) and a React frontend (`frontend/`) that calls it.

## Running both together

```
cd backend
.venv/bin/uvicorn api:app --reload --port 8000
```

```
cd frontend
npm run dev
```

The frontend's dev server runs on `localhost:5173` by default, which the backend's CORS config already allows (see Backend setup below).

---

## Backend

### Claims Agent

Produces two things: a structural reading (which claims are independent, which depend on which — cheap and reliable), and a protection-scope reading for each independent claim (broad/narrow, defensive/offensive/exploratory — judgment-based, uses the Claude API).

#### How the data is fetched

Claims text comes from Google's public patent dataset on BigQuery: `patents-public-data.patents.publications`, specifically the `claims_localized` array field.

Setup:
```
pip install google-cloud-bigquery
gcloud auth application-default login
gcloud config set project <your-project-id>
```

Create a BigQuery project and link a real billing account. The first 1 TiB of query processing per month is free, but be aware of the real cost past that: this specific table has no clustering or partitioning on `publication_number`, so a lookup for even a single patent scans the relevant columns across the entire ~98 million row table — about 116 GB per new lookup in practice, roughly $0.71 at the standard $6.25/TiB on-demand rate.

Two things that make this manageable:
- Always query by exact `publication_number` match, using a parameterized query (`WHERE publication_number = @pub_number`) — never `LIKE`.
- BigQuery caches identical query results. Re-running the exact same query against the same patent is free. All test scripts reuse the same known set of patents for this reason — check `test_connection.py`, `test_real_parse.py`, `test_multi_dependent.py`, `test_broader_domains.py`, `test_lineage_agent.py`, and `test_lineage_broader.py` for the specific publication numbers already paid for and cached.

A smaller, cheaper-looking table (`patents-public-data.uspto_oce_claims.patent_claims_fulltext`, ~29 GB total) was checked and rejected — it was last updated in 2017 and doesn't cover any patents granted after that.

#### How the Claude API is set up

Protection-scope classification uses the Claude API directly (not BigQuery's built-in AI functions), since the classification logic needed to be testable and iterable outside of SQL.

```
pip install anthropic fastapi uvicorn python-dotenv
```

Create a `.env` file in `backend/` with:
```
ANTHROPIC_API_KEY=your-key-here
```

`api.py` calls `load_dotenv()` on startup, so the key loads from this file automatically — no manual `export` needed in any terminal session. (Earlier versions of this backend required exporting the key manually in the exact terminal session running `uvicorn`, which silently broke every time that terminal tab closed; this was fixed by adding `python-dotenv`.)

Get a key at console.anthropic.com → Settings → API Keys. New accounts get $5 in trial credit, which comfortably covers this project's usage — each claim classification call is roughly 700-800 input tokens and under 200 output tokens, a small fraction of a cent at Claude Sonnet 5's per-token rate.

A real limitation to know about: the model will refuse to classify claims whose subject matter touches certain sensitive categories (hit this on a real patent about plant cell cultures producing a pharmaceutical compound — `stop_reason` came back as `"refusal"`, category `"bio"`). `claim_classifier.py` handles this by returning an `"unclear"` classification with an explicit note in the confidence caveat, rather than crashing — but it means some real patents, especially in biotech and pharma, won't get an automated scope reading at all. Tested against 3 more real patents spanning mechanical, robotics, and minimally-invasive-surgery domains — zero refusals on that batch, so the refusal case is real but not yet common in the patents tried so far.

#### A real parsing gap found and fixed

Broader-domain testing (`test_broader_domains.py`) found a real bug: `US-12551228-B2` uses `"1 ."` (a space before the period) for claim numbering instead of the `"1."` format seen in every patent tested up to that point. The original regex required the period immediately after the digits, so it silently returned 0 claims for a patent that genuinely had 14. Fixed by allowing optional whitespace between the number and the period — verified against both formats before and after the fix (see `inspect_parse_failure.py`).

Open question, not yet explained: every independent claim classified so far across the 3 broader-domain patents came back "narrow/defensive" — six claims in a row with no "broad" or "offensive" reading. Could reflect how those particular patents are actually drafted, or could be a real bias in the classifier. Worth watching, not yet concluded either way.

### Lineage Agent — backward citations

`lineage_agent.py` traces a patent's citation lineage. Covers backward citations only — what a patent cites — since that's a direct field (`citation`, a REPEATED RECORD) on the same row already being queried for claims text, genuinely cheap with no separate lookup needed.

Forward citations (who cites this patent) are not implemented — would require a different, likely much more expensive query pattern, deliberately deferred.

A real bug was found and fixed while building this: BigQuery returns empty strings, not `None`, for missing fields in this table's citation records. The original `is_non_patent_literature` check used `npl_text is not None`, always true here. Fixed to check for genuinely non-empty text. Verified against real data (`US-10822628-B2`, 12 real citations: 1 patent, 11 academic papers, confirmed by hand).

Broadened to 2 more real patents (`test_lineage_broader.py`): `US-11983488-B1` (OpenAI) came back with 20 citations, 18 of them real patents, including real non-US publication numbers (`CN-103154936-A`, `WO-2022015730-A1`), confirming the parser handles international formats correctly. `US-2024160902-A1` (Shopify) came back with just 3 citations, the smallest count tested so far. A genuine zero-citation patent was not found and tested — remains untried.

Also observed but not yet acted on: the `category` field sometimes contains comma-separated values (e.g. `"APP,APP"`, `"SEA,SEA"`) rather than a single code — worth understanding before using `category` for anything downstream.

### FastAPI backend — a real HTTP interface

`api.py` wraps the exact same logic as `patent_reader.py` behind a real HTTP endpoint, so a frontend (or any other client) can call it instead of shelling out to a CLI.

```
GET /patent/{publication_number}?classify=true|false
```

`classify` defaults to `true` and mirrors the CLI's `--no-classify` flag: it lets a caller skip the real, fresh Claude API cost when only the free structural and lineage reading is needed.

Verified against the same two real patents used to verify the CLI itself: `US-10822628-B2` with `classify=false` (matched the independently-verified 7/2/5 claim split and 12-citation lineage exactly, zero new cost) and `US-11197952-B2` with classification on (matched the same real 17/1/16 claim split and a real, well-reasoned classification, at the real small Claude API cost).

CORS is configured for `localhost:5173` and `localhost:3000` (common Vite/React dev server ports) — the frontend in `frontend/` runs against this.

### What's tested, and how confident to be in each part

| Component | Tested against | Confidence |
|---|---|---|
| `claims_parser.py` split/classify | 7 real patents, 82 claims total, verified by hand | High — every claim correct, including a real formatting-variant fix |
| `flag_multi_dependency` | Original 4 patents; one confirmed false-positive found and fixed | High, after the fix |
| `claim_classifier.py` scope reading | 8 real independent claims across 4 patents, 4 domains | Moderate — every result well-reasoned with checkable caveats, but the "always narrow/defensive" pattern is an open question |
| `lineage_agent.py` backward citations | 4 real patents, citation counts from 3 to 242, 7 jurisdiction formats | High — field-access pattern, empty-string fix, and international formats all confirmed; zero-citation case still untested |
| `patent_reader.py` combined CLI | 2 real patents, both structural-only and full-pipeline modes | Moderate-high — matches independently-verified agent output exactly |
| `api.py` FastAPI backend | 2 real patents, both `classify=false` and `classify=true` | Moderate-high — matches already-verified CLI output exactly; now tested with a real frontend, not yet under concurrent load |

### Files

- `claims_parser.py` — split/classify logic, handles two known claim-numbering formats
- `claim_classifier.py` — Claude-based protection-scope classification
- `claims_agent.py` — the `ClaimsAgent` class wiring both together
- `lineage_agent.py` — the `LineageAgent` class, backward citations only so far
- `test_connection.py` — verifies BigQuery access end-to-end
- `test_real_parse.py` — pulls and parses one real patent's full claims text
- `test_multi_dependent.py` — stress test against 3 more real patents
- `test_broader_domains.py` — broader domain test that found the claim-numbering format bug
- `inspect_parse_failure.py` — the investigation that found the real cause of the format bug
- `inspect_independent_claims.py` — structural stats across known independent claims — the real evidence that these don't cleanly predict scope, which is why classification uses an LLM call rather than a heuristic
- `test_classifier_first_run.py` — first real test of the classifier alone
- `test_claims_agent.py` — real end-to-end test of the full `ClaimsAgent` class
- `test_lineage_agent.py` — first real test of `LineageAgent`, including the field-access verification that found the empty-string bug
- `inspect_all_citations.py` — the investigation that confirmed the empty-string fix was correct
- `test_lineage_broader.py` — broadened `LineageAgent` testing to 2 more real patents
- `patent_reader.py` — the real, callable CLI wiring `ClaimsAgent` and `LineageAgent` together
- `api.py` — the real FastAPI backend wrapping both agents behind an HTTP endpoint

---

## Frontend

A React (Vite) single-page UI calling the backend above: one input for the publication number, a checkbox to toggle classification on or off, and a result view built directly from the real API response shape — not from assumed field names.

Renders two sections per result:
- **Claims** — total/independent/dependent counts, plus (when `classify=true`) a per-claim scope reading: breadth, posture, and the model's own confidence caveat, and a flagged-for-manual-review note when present.
- **Lineage** — total/patent/non-patent-literature citation counts, with an expandable list of cited publication numbers.

### Running it

```
cd frontend
npm install
npm run dev
```

Requires the backend running at `http://127.0.0.1:8000` (see `API_BASE` in `src/App.jsx`).

### What's tested

Verified end-to-end against both real response shapes: `classify=false` (claim/citation counts only) and `classify=true` (the full scope-reading output), using the same two patents the backend itself was verified against (`US-10822628-B2`, `US-11197952-B2`).

---

## Not built yet

- A conversational Q&A layer (ask a free-form question about a patent and get an answer) — deliberately scoped as a separate future milestone, not part of this build.
- Wiring the agents into a production deployment (currently runs locally via `uvicorn` + Vite dev server, not deployed).
- Forward citations in the Lineage Agent — deliberately deferred, real query cost untested.
- Explaining the "always narrow/defensive" classifier pattern — more real patents needed.
- A genuine zero-citation patent — not yet found and tested.
- Frontend behavior under concurrent load or against a deployed (non-local) backend.
