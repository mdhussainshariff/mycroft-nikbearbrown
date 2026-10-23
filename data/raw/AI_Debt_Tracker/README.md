# AI Debt Tracker

The AI build-out is increasingly paid for with borrowed money. This agent keeps an always-up-to-date
ledger of every bond and loan that ~25 AI-sector companies (cloud, chips, data centres, power, AI
software) owe — principal, interest rate, due date — built from SEC filings as they appear, and turns
it into a quarterly signal for Mycroft: total debt, new borrowing, the maturity wall (how much falls
due in the next 12–24 months), and the average interest rate.

It is graded against each company's next quarterly report, which tags debt per instrument, and it
runs on local models only (Ollama on an 8 GB laptop GPU) — no paid APIs.

## Status

**Week 2 complete — gate cleared 2026-10-23.** The answer key covers all 100 companies, the grader
scores at three levels, and the do-nothing baseline is measured: it finds 90.7% of bonds but none of
the 36 new ones. The grader agrees with 10 of 10 hand-checked printed debt tables (2 of 3 held out),
accepted by Om Mali (`manifests/week2_gate.json`). Week 1 is frozen (`manifests/week1_gate.json`).

- [`docs/answer_key.md`](docs/answer_key.md) — the answer key for every report, with its anomalies.
- [`docs/baseline_b0.md`](docs/baseline_b0.md) — baseline B0 (carry forward) scored on dev.
- [`docs/handcheck.md`](docs/handcheck.md) — the grader against printed debt tables; the Week 2 check.
- [`docs/changes_dev.md`](docs/changes_dev.md) — which bond changes were announced in a filing.

- [`DESIGN.md`](DESIGN.md) — data sources, problems and fixes (P1–P29), agents, MCP servers,
  models, evaluation, ten-week plan.
- [`docs/feasibility.md`](docs/feasibility.md) — every go/no-go check with its pass line and result,
  including the Week 1 re-runs.
- [`docs/universe_v1_review.md`](docs/universe_v1_review.md) → [`universe_v1.json`](universe_v1.json)
  — measured grading level, subsidiaries and coverage for the 25 companies (frozen).
- [`manifests/`](manifests) — `generalisation.csv` (75 companies), `dev.csv` (95 episodes),
  `test.csv` (400 episodes), all frozen; `week1_gate.json` (who cleared it, and on what basis);
  `bakeoff_truth_corrections.json`.
- [`docs/answer_key_week1.md`](docs/answer_key_week1.md) — the answer key for 10 companies.
- [`docs/bakeoff.md`](docs/bakeoff.md), [`docs/bakeoff_set.md`](docs/bakeoff_set.md) — the model
  bake-off and its 29 documents, each checked.
- [`docs/worklog.md`](docs/worklog.md) — what was done, week by week.

## Where things live

The repo holds code, documents and small manifests. Everything bulky lives in a local directory
**outside the repo**, configured in `.env` (gitignored):

| What | Configured by | In git? |
|---|---|---|
| Code, docs, manifests, small fixtures | this folder | yes |
| Filing cache, SEC monthly notes zips, run outputs | `AI_DEBT_DATA` (optionally reached through a `data` link in this folder) | no |
| Python environment | `UV_PROJECT_ENVIRONMENT` | no |
| Package cache | `UV_CACHE_DIR` | no |
| Model weights (`qwen3:8b`, 4.9 GB) | `OLLAMA_MODELS` | no |

One-time setup (PowerShell, from this folder):

```powershell
Copy-Item .env.example .env        # then fill in EDGAR_NAME / EDGAR_EMAIL and the local paths
# optional: let scripts find the data directory without AI_DEBT_DATA set
New-Item -ItemType Junction -Path data -Target <your AI_DEBT_DATA directory>
```

The scripts read `.env` automatically (`scripts/_localenv.py`); variables already set in the shell
win.

**Running Ollama against the project's model directory.** Ollama reads `OLLAMA_MODELS` from its own
environment, so start it with that set:

```powershell
$env:OLLAMA_MODELS = "<your models directory>"; ollama serve
```

**Python environment** (uv, outside the repo through `UV_PROJECT_ENVIRONMENT`):

```powershell
$env:UV_PROJECT_ENVIRONMENT = "<your venv directory>"; $env:UV_CACHE_DIR = "<your uv cache>"
uv sync                      # Python 3.11+, installs mcp (<2), scipy and pytest
uv run pytest                # 95 offline tests: parser, matcher, answer key, grader, B0, edgar_pit's cut-off rule
```

## Reproducing Week 1

Run in this order; each step reads the previous one's output (`PYTHONPATH=scripts` lets the
scripts share helpers):

```powershell
$env:PYTHONPATH = "scripts"
uv run python -m ai_debt_tracker.eval.fsn 2024_07 2026_09 3   # SEC notes data -> debt subset (2.8 GB zips, ~10 min)
uv run python scripts/review_universe.py                        # -> universe_v1.json, docs/universe_v1_review.md
uv run python scripts/select_generalisation.py                  # -> manifests/generalisation.csv
uv run python scripts/build_splits.py                           # -> manifests/dev.csv, manifests/test.csv
uv run python scripts/load_answer_key.py                        # -> docs/answer_key_week1.md
uv run python scripts/f1_matching.py dev                        # F1 re-run
uv run python scripts/bakeoff.py build                          # -> docs/bakeoff_set.md
uv run python scripts/bakeoff.py run qwen3:8b                   # Ollama running (see above)
uv run python scripts/bakeoff.py run qwen3:4b
uv run python scripts/bakeoff.py report                         # -> docs/bakeoff.md
```

The frozen steps (`review_universe.py`, `select_generalisation.py`, `build_splits.py`) now refuse to
overwrite their outputs; `--refreeze` exists only for use with a new, logged gate decision.

## Reproducing Week 2

```powershell
$env:PYTHONPATH = "scripts"
uv run python -m ai_debt_tracker.eval.fsn 2024_01 2024_06 2     # earlier notes data (prior 10-Ks)
uv run python scripts/build_answer_key.py                       # -> docs/answer_key.md
uv run python scripts/score_baseline.py dev                     # -> docs/baseline_b0.md
uv run python scripts/handcheck.py grade                        # -> docs/handcheck.md (transcriptions in manifests/handcheck/)
uv run python scripts/explain_changes.py                        # -> docs/changes_dev.md
```

**The `edgar_pit` MCP server** (point-in-time EDGAR for the agent): one process per episode,
configured by the environment. It refuses the target report and anything accepted after it, and
logs every call to `$AI_DEBT_DATA/logs/edgar_pit_access.jsonl`. Start it from the episode's target
report — not from a timestamp, because EDGAR's acceptance times have moved by hours (P29):

```powershell
$env:EDGAR_PIT_TARGET = "<cik>:<target_adsh>"                   # both columns of manifests/*.csv
uv run python -m ai_debt_tracker.mcp_servers.edgar_pit          # stdio; tools: timeline, exhibits, fetch
```

## Reproducing the feasibility numbers (Week 0)

```powershell
python scripts/probe_debt_filings.py                                  # filing counts, tagging detail
python scripts/spike_f1_f3_matching_and_headroom.py                   # F1 matching, F3 headroom
python scripts/spike_f2_f4_announcements_and_model.py qwen3:8b all    # F2 announcements, F4 model (Ollama running)
```
