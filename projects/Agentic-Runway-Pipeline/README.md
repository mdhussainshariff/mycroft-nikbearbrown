# Agentic Runway-Risk Intelligence Pipeline

An AI agent gathers the evidence; a deterministic pipeline validates, scores, and
halts for a human. This is the production-grade extension of the delivered
runway-risk-scorer (RUNNABLE-SAMPLE) — the same provenance-first, human-gated core,
now fed by an autonomous real-data front end.

> **Design principle (unchanged from the original):** the AI *gathers* evidence;
> it never *decides* risk. A human makes the final judgment at the gate.

---

## What this project does

Given a company name, the pipeline:

1. **Gathers** — an AI research agent decides which sources to search, reads what it
   finds, judges whether it has enough, and loops until it does.
2. **Extracts** — an LLM turns the agent's raw findings into structured signals
   (amount, date, type).
3. **Validates** — every signal is checked against a typed schema; malformed records
   are rejected at the door.
4. **Halts at a human gate** — a person validates the signals before they count (P2).
5. **Scores** — the existing runway-risk metrics run on the validated signals.
6. **Stores & serves** — each run is persisted; results are served via an API and
   dashboard.

It never issues a verdict. It computes and sources the inputs; the human decides.

---

## Architecture

```
Company name
  → Research agent      (LangGraph: plan → search → read → 'enough?' → loop)
  → LLM extraction      (LangChain; local Llama via Ollama)
  → Embedding dedup     (sentence-transformers)
  → Schema validation   (pydantic — reject malformed records)
  → HUMAN VALIDATION GATE (P2)
  → Scoring             (the runway-risk metrics)
  → Storage             (DuckDB — run history over time)
  → Serving             (FastAPI API + Streamlit dashboard)
  → Orchestration       (Apache Airflow — scheduled refresh)
```

---

## The stack

| Concern | Tools / libraries |
|---|---|
| Agentic orchestration | LangGraph (agent state machine: search / read / decide / loop) |
| LLM + extraction | LangChain; Anthropic/OpenAI SDK or local Llama via Ollama |
| Search / ingestion | httpx / requests, feedparser (RSS), a news/search API |
| Dedup | sentence-transformers (embed signals, cosine-match duplicates) |
| Schema validation | pydantic (typed models; reject malformed records) |
| Storage + history | DuckDB (analytical queries, run history) |
| Serving | FastAPI (API), Streamlit (dashboard) |
| Orchestration | Apache Airflow (scheduled refresh) — or Prefect |

---

## The 8-sprint plan

| Sprint | Dates | Focus | What it delivers |
|---|---|---|---|
| 1 | 09/14–09/18 | Foundation & Schema | Typed pydantic schema; wire basic ingestion (httpx + feedparser + a news API) for 3–5 real AI vendors. Sample set kept as a test fixture. |
| 2 | 09/21–09/25 | LangGraph Agent Skeleton | Research agent as a state machine: plan → search → read → 'enough?' → loop, with a hard stop condition. Every decision logged. Control flow only. |
| 3 | 09/28–10/02 | LLM Extraction (LangChain) | LangChain structured output turning the agent's findings into typed signals (amount, date, type), against an API model. Human gate retained. |
| 4 | 10/05–10/09 | Local Model (Llama/Ollama) | Swap extraction to a local Llama via Ollama (cost/privacy). Compare quality vs. the API model and log the difference. |
| 5 | 10/12–10/16 | Dedup & Scorer Integration | Embedding dedup (sentence-transformers) so one event from two sources counts once. Feed validated signals into the scoring logic. Full path working. |
| 6 | 10/19–10/23 | Storage & Trend History | Persist every run to DuckDB. Per-brief confidence score and a first risk-over-time trend view. |
| 7 | 10/26–10/30 | Serving & Orchestration | FastAPI endpoint + Streamlit dashboard (comparison, trend charts). Schedule with Airflow. |
| 8 | 11/02–11/06 | Hardening, Attestation & PR | Break tests for the new components. Updated attestation (agent limits, real-data caveats, LLM-proposed vs. human-accepted). Open a PR; advance toward RUNNABLE-LIVE. |

---

## Status

**Current sprint:** 1 (Foundation & Schema) — schema + validator built and tested on
sample data; real-data ingestion in progress.

**Committed ceiling:** RUNNABLE-LIVE for a small set of real AI vendors. This is a
strong portfolio pipeline, not a commercial product.

---

## Honest limits & guardrails

- **The AI gathers; it never judges.** Every signal the agent/LLM produces is
  human-validated before it counts. The risk decision stays with a human.
- **The agent can be wrong.** It can miss or misread sources — so every signal is
  confidence-scored, and agent decisions are logged so failures are auditable.
- **Private companies have thin data.** Signals are news/funding-grade, not SEC-grade.
  The confidence score and human gate exist precisely for this.
- **Scope honestly.** A small vendor set and a working end-to-end system. Each sprint
  is finishable; don't half-build every layer.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run (Sprint 1)

```bash
python -m ingest.load_signals data/samples/sample_signals.json
```
Expected: valid signals pass; malformed ones are rejected with reasons.

---

## Relationship to the runway-risk-scorer

This project reuses the scorer's metrics, provenance rule, and human gate unchanged.
It adds the agentic gathering, LLM extraction, and production data-engineering layers
around that core. The scorer is the deterministic heart; this is the intelligent,
real-data body built around it.
