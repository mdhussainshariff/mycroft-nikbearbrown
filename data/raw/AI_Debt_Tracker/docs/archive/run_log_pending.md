# Pending entry for `logs/RUN_LOG.md`

`logs/RUN_LOG.md` is a shared, append-only file at the repo root, and the working tree is currently
on another project's branch. To avoid a branch conflict, this entry waits here. After creating the
`feature/ai-debt-tracker` branch, append everything below the line to `logs/RUN_LOG.md`, then
archive this file (move it to `docs/archive/`, per the never-delete rule).

---

## 2026-10-16 -- AI Debt Tracker: Week 0, design and feasibility spike

- **Recipe:** `data/raw/AI_Debt_Tracker/DESIGN.md` (new project; ten-week plan in §11).
- **Gate decision:** **F0 mission fit -- approved by the professor** (reported by Om Mali, 2026-10-16; the written OK is attached to the project PR). Overall feasibility verdict: **go**, recorded in `docs/feasibility.md`.
- **Commands:** `python scripts/probe_debt_filings.py`; `python scripts/spike_f1_f3_matching_and_headroom.py`; `python scripts/spike_f2_f4_announcements_and_model.py qwen3:8b all`; `node scripts/conformance.mjs data/raw/AI_Debt_Tracker` -> conforms.
- **Inputs:** EDGAR submissions API and filing archives for the 25-company universe (`universe_draft.json`); SEC Financial Statement and Notes monthly data sets 2025-12 .. 2026-09 (cached locally under `AI_DEBT_DATA`, not in git).
- **Outputs:** `DESIGN.md`, `README.md`, `universe_draft.json`, `docs/feasibility.md`, `docs/worklog.md`, `scripts/*.py`; run data under `$AI_DEBT_DATA/spike` (episodes, F4 raw answers; local, not in git).
- **Results (46 company-quarters, reports filed Dec 2025 -- Sep 2026):** 56 of 64 real new bonds (87.5%) explained by an announcement (F2 pass); carry-forward misses an announced change in 21 of 46 (F3 pass); 489 of 588 instruments matched across reports (83%, F1 partial -- causes P17--P21 added to the design); `qwen3:8b` naive single-call extraction 69/79 fields (87%), 3.7 s per document, 5.3 GB VRAM (F4 pass, narrow; principal 7/13 is the weak field).
- **Model judgments:** none published. The F4 answers are model output used only for measurement.
- **Open issues:** answer-key rates in the bulk data are rounded (P17) -- use Arelle for exact values; Alphabet and Amazon reclassified to offering-level grading (P18); annual-vs-quarterly tagging detail differs (P19, Intel 42 -> 1); removal explanations are noisy and need a proper method in week 2; `qwen3:4b` not yet tested.

## 2026-10-18 -- AI Debt Tracker: Week 1, universe measured, answer key, edgar_pit, F1 re-run, model bake-off

- **Recipe:** `data/raw/AI_Debt_Tracker/DESIGN.md` §11 week 1.
- **Gate decisions:** none cleared in this entry (see the gate entry below). Ollama kept at 0.34.0 (Om Mali, 2026-10-18; a set-up choice, not a gate). **Pending at the time, for a named human:** freeze `universe_v1.json` and `manifests/generalisation.csv` (and with them `manifests/dev.csv` / `test.csv`); attest `docs/bakeoff_set.md` and confirm the model.
- **Commands:** `python -m ai_debt_tracker.eval.fsn 2024_07 2026_09 4`; `scripts/review_universe.py`; `scripts/select_generalisation.py`; `scripts/build_splits.py`; `scripts/load_answer_key.py`; `scripts/f1_matching.py dev` and `test`; `scripts/bakeoff.py build | run qwen3:8b | run qwen3:4b | report`; `uv run pytest` -> 65 passed; `node scripts/conformance.mjs data/raw/AI_Debt_Tracker` -> conforms.
- **Inputs:** SEC Financial Statement and Notes data 2024q3..2025q3 (quarterly) and 2025_10..2026_09 (monthly), 2.8 GB, under `AI_DEBT_DATA` (not in git); EDGAR submissions index and filing headers for 25 + 75 companies; 29 dev-window announcements fetched through `edgar_pit`.
- **Outputs:** `pyproject.toml`, `uv.lock`, `src/ai_debt_tracker/` (config, sec, edgar, eval/fsn, eval/answer_key, ledger/parsers, ledger/matcher, mcp_servers/edgar_pit_core, mcp_servers/edgar_pit), `tests/` (4 files), `scripts/` (6 new), `universe_v1.json`, `manifests/{generalisation,dev,test}.csv`, `docs/{universe_v1_review,answer_key_week1,bakeoff,bakeoff_set}.md`; DESIGN.md (P22--P29, measured levels, split counts, layout), feasibility.md, worklog.md, README.md updated.
- **Results:** universe levels by coverage of total debt L1 14 / L2 3 / L3 8 (draft 21 / 3 / 1); episodes dev 95, test 100 AI + 300 generalisation, 0 dropped; F1 on L1-graded episodes dev 594/636 = 93.4%, test 696/767 = 90.7% (pass; all episodes 85.0% / 82.2%); bake-off on 29 announcements, no hints: `qwen3:4b` 138/145 fields = 95%, 29/29 JSON, max 12.6 s (pass, provisional pick); `llama3.1:8b` 88%, `qwen3:8b` 84% with 2--3 runaway answers each.
- **Model judgments:** none published. Bake-off answers are model output used only for measurement; the bake-off truth is the next report's XBRL, awaiting human attestation.
- **Open issues:** universe/generalisation/splits/model pick unsigned (P4); the bake-off set has 29 documents, not 30, and almost no redemption notices or credit agreements (the dev window had few early redemptions among these companies); Week 0's F4 prompt named the coupon, so its 87% is not comparable with the bake-off; Meta and TeraWulf company levels are 4--4 ties resolved to the coarser level; `universe_draft.json` stays until the freeze, then moves to `docs/archive/`.

## 2026-10-18 -- AI Debt Tracker: Week 1 gate cleared

- **Recipe:** `data/raw/AI_Debt_Tracker/DESIGN.md` §11 week 1, end-of-week check.
- **Gate decision:** **Cleared by Om Mali, 2026-10-18** -- universe v1 frozen (overrides: Meta L3 -> L2, TeraWulf L3 -> L1, reasons in `manifests/week1_gate.json`), generalisation set and dev/test splits frozen, bake-off set accepted with 7 truth corrections, model `qwen3:4b` confirmed. **Basis:** Claude's review (`docs/week1_review.md`, a model judgment per P8); Om accepted it without checking the filings personally, and the record says so.
- **Commands:** `scripts/review_universe.py`, `scripts/select_generalisation.py`, `scripts/build_splits.py` (re-run with the gate file: statuses FROZEN, splits unchanged at 95 / 400); `scripts/bakeoff.py setdoc`, `scripts/bakeoff.py report`.
- **Outputs:** `manifests/week1_gate.json`, `manifests/bakeoff_truth_corrections.json`, `docs/week1_review.md` (new); `universe_v1.json`, `manifests/*.csv`, `docs/universe_v1_review.md`, `docs/bakeoff.md`, `docs/bakeoff_set.md` regenerated.
- **Results:** bake-off re-scored after the corrections: `qwen3:4b` 141/143 = 99%, `llama3.1:8b` 91%, `qwen3:8b` 88%; universe L1 15 / L2 4 / L3 6.
- **Open issues:** the 10 company-quarter hand-check against printed debt tables is still a Week 2 task; redemptions and credit agreements are not covered by the bake-off.
