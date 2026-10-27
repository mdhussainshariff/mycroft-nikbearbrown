"""Purpose: Quality-check the shape-verified signals and assemble, per declared company, exactly the rows the original workflow's queries would return.
Input: shape-verified sources from step 3 (data/verified/contradiction-detection-agent/runs/<run>/<source>.json) and the run envelope (companies, lookback_days, frozen_clock).
Output: one bundle per company at data/verified/contradiction-detection-agent/runs/<run>/quality-checked/<TICKER>.json ({ctx, rows, selection}), plus a report on stdout (and --output) with verified_records, record_count, duplicates, rejects, flags, quality_notes.
Side effects: writes into data/verified/ only. No network.
Idempotent: Yes; all dates are measured against the envelope's frozen_clock.
Recipe: recipes/contradiction-detection-agent.md

What it withholds, and why. Each withheld row is listed with its reason (an audit that removes rows
silently certifies nothing):
  - exact duplicate `id` within a source: the first is kept, later copies are withheld
  - `schema_valid` not true: withheld, as the original queries' `WHERE ... schema_valid = true` does
  - ticker not among the declared companies: withheld (out of declared scope)

What it reports but deliberately does NOT withhold:
  - rows older than the declared `lookback_days`. The original's five queries select without a date
    filter, so reproducing its results means keeping these rows; the report counts them so a human can
    see how much older evidence the detector is weighing.
  - rows cut by a query LIMIT: counted per company and source.

Selection (`select_like_original_sql`) reproduces each query's WHERE / ORDER BY / LIMIT exactly; the
parity check imports this same function, so the pipeline and the parity test can't drift apart.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

WORKFLOW_NAME = "Contradiction_detection_agent"
WORKFLOW_SLUG = "contradiction-detection-agent"
NODE_NAME = "Transform and quality check"
NODE_TYPE = "recipe-step"
CLASSIFICATION = "gigo"
ROOT = Path(__file__).resolve().parents[2]
SOURCES = ["guidance-signals", "risk-admissions", "qa-pressure-map", "news-signals", "tech-stack-signals"]

# Each original SQL node's ORDER BY and LIMIT (all filter on ticker and schema_valid = true).
ORIGINAL_QUERY = {
    "guidance-signals":   ("DB: Fetch Earnings Guidance Signals", [("call_date", True), ("direction_confidence", True)], 50),
    "risk-admissions":    ("DB: Fetch Risk Admissions", [("call_date", True), ("severity", True)], 30),
    "qa-pressure-map":    ("DB: Fetch QA Pressure Map", [("call_date", True), ("pressure_score", True)], 30),
    "news-signals":       ("DB: Fetch News Signals", [("published_at", True)], 50),
    "tech-stack-signals": ("DB: Fetch Tech Stack Signals", [("snapshot_date", True)], 10),
}
DATE_FIELD = {"guidance-signals": "call_date", "risk-admissions": "call_date", "qa-pressure-map": "call_date",
              "news-signals": "published_at", "tech-stack-signals": "snapshot_date"}


def select_like_original_sql(rows: list[dict], source: str, ticker: str) -> tuple[list[dict], list[dict]]:
    """WHERE ticker = <t> AND schema_valid = true ORDER BY <keys> LIMIT <n>. Returns (selected, cut_by_limit).
    Values sort as stored (severity is stored as text, so it sorts alphabetically)."""
    _, keys, limit = ORIGINAL_QUERY[source]
    sel = [r for r in rows if r.get("ticker") == ticker and r.get("schema_valid") is True]
    for key, desc in reversed(keys):  # stable multi-key sort: last key first
        sel.sort(key=lambda r: (r.get(key) is None, r.get(key) if r.get(key) is not None else ""), reverse=desc)
    return sel[:limit], sel[limit:]


def ctx_for(company: dict, env: dict) -> dict:
    """The original's 'Set Company Input' values, with its clock replaced by the frozen clock."""
    day = env["frozen_clock"][:10].replace("-", "")
    return {"ticker": company["ticker"], "company_name": company["company_name"],
            "lookback_days": env.get("lookback_days", 365), "fiscal_quarter": "",
            "active_patterns": env.get("active_patterns", [1, 2, 3, 4, 5, 6]),
            "resolve_id": f"CONTRA-{company['ticker']}-{day}-001", "requested_at": env["frozen_clock"],
            "frozen_clock": env["frozen_clock"]}


def emit(data: Any, output: str | None) -> None:
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    print(text)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--envelope", default=str(ROOT / f"data/raw/{WORKFLOW_SLUG}/run-envelope.json"))
    ap.add_argument("--fixture-set", choices=["clean", "defective"])
    ap.add_argument("--output")
    a = ap.parse_args()
    env = json.loads(Path(a.envelope).read_text(encoding="utf-8"))
    run = f"{env['run_id']}-{a.fixture_set or env['fixture_set']}"
    vdir = ROOT / f"data/verified/{WORKFLOW_SLUG}/runs/{run}"
    clock = datetime.fromisoformat(env["frozen_clock"])
    cutoff = (clock - timedelta(days=env.get("lookback_days", 365))).date().isoformat()
    declared = {c["ticker"] for c in env["companies"]}
    stops, rejects, duplicates, stale, kept = [], [], [], [], {}
    for source in SOURCES:
        p = vdir / f"{source}.json"
        if not p.exists():
            stops.append(f"{source}: no shape-verified file (step 3 did not promote it)")
            kept[source] = []
            continue
        seen, out = set(), []
        for r in json.loads(p.read_text(encoding="utf-8"))["records"]:
            if r["id"] in seen:
                duplicates.append({"source": source, "id": r["id"], "action": "withheld (later copy)"})
                continue
            seen.add(r["id"])
            if r.get("schema_valid") is not True:
                rejects.append({"source": source, "id": r["id"], "reason": "schema_valid is not true (the original query excludes it)"})
                continue
            if r.get("ticker") not in declared:
                rejects.append({"source": source, "id": r["id"], "reason": f"ticker {r.get('ticker')!r} is outside the declared companies"})
                continue
            if str(r.get(DATE_FIELD[source], ""))[:10] < cutoff:
                stale.append({"source": source, "id": r["id"], "date": r.get(DATE_FIELD[source]),
                              "note": f"older than lookback ({cutoff}); kept, as the original queries select without a date filter"})
            out.append(r)
        kept[source] = out
    out_dir = vdir / "quality-checked"
    per, limit_cuts = [], []
    # A stopped step leaves no half-built input behind: bundles missing a source would look complete to step 5.
    for company in ([] if stops else env["companies"]):
        t = company["ticker"]
        rows, selection = {}, {}
        for source in SOURCES:
            sel, cut = select_like_original_sql(kept[source], source, t)
            rows[source] = sel
            selection[source] = {"original_node": ORIGINAL_QUERY[source][0], "returned": len(sel), "cut_by_limit": len(cut),
                                 "cut_ids": [r["id"] for r in cut]}
            if cut:
                limit_cuts.append({"ticker": t, "source": source, "cut": len(cut),
                                   "cut_severities": sorted({r.get("severity") for r in cut if "severity" in r})})
        write_json(out_dir / f"{t}.json", {"ctx": ctx_for(company, env), "rows": rows, "selection": selection,
                                           "run": run, "checked_at": env["frozen_clock"]})
        per.append({"ticker": t, "rows": {s: len(rows[s]) for s in SOURCES}})
    record_count = sum(len(v) for v in kept.values())
    notes = [f"{len(stale)} row(s) older than the declared {env.get('lookback_days', 365)}-day lookback were kept "
             "(the original queries select without a date filter)." if stale else "No row is older than the declared lookback.",
             f"{len(limit_cuts)} company/source selection(s) were cut by a query LIMIT." if limit_cuts
             else "No query LIMIT cut any row."]
    flags = ([{"flag": "STALE_EVIDENCE_KEPT", "count": len(stale)}] if stale else []) + \
            ([{"flag": "LIMIT_TRUNCATION", "detail": limit_cuts}] if limit_cuts else [])
    emit({"workflow": WORKFLOW_NAME, "node": NODE_NAME, "node_type": NODE_TYPE, "classification": CLASSIFICATION,
          "run": run, "verified_records": record_count, "record_count": record_count, "duplicates": duplicates,
          "rejects": rejects, "stale_rows": stale, "flags": flags, "quality_notes": notes, "companies": per,
          "output_path": str(out_dir.relative_to(ROOT)), "status": "stop" if stops else "ok", "stop_conditions": stops,
          "live_call_performed": False, "network_access": "none", "next_step": None if stops else "run-approved-tools",
          "human_gate": {"gate": 3, "capacity": "[PA]", "cleared_by": None,
                         "note": "A human reads the withheld rows and the kept-but-stale rows before detection runs."}},
         a.output)
    return 1 if stops else 0


if __name__ == "__main__":
    raise SystemExit(main())
