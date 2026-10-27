"""Purpose: Check every ingested row against the field contract of the query that produces it, and promote only shape-clean rows into the verified layer.
Input: the raw envelopes from step 2 (data/raw/contradiction-detection-agent/runs/<run>/<source>.json).
Output: per source, data/verified/contradiction-detection-agent/runs/<run>/<source>.json holding only shape-clean rows, plus a findings report on stdout (and --output) with record_count, required_fields_present, missing_fields, type_errors, parse_errors, schema_version.
Side effects: writes into data/verified/ only. No network.
Idempotent: Yes; output depends only on the raw envelopes.
Recipe: recipes/contradiction-detection-agent.md

Where the contract comes from. Each source stands for one SQL node of the original workflow, and the
contract below is that node's SELECT list (aliases as the query returns them), with types chosen from
how the detection logic uses each field. "Required" means the detection logic reads it.

What this step owns: shape. A file that doesn't parse, a row that isn't an object, a required field that
is absent or null, a value of the wrong type, a label outside its allowed set, and a value outside a
documented bound. It does NOT judge duplicates, tickers, staleness or `schema_valid` (step 4 owns those).

Halting. A shape failure is not an early exit: every finding in every source is reported first, the
clean rows are still promoted, and then the step returns status "stop" with exit 1, so a downstream step
can't run on a partially valid layer without a human seeing the report (P4).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

WORKFLOW_NAME = "Contradiction_detection_agent"
WORKFLOW_SLUG = "contradiction-detection-agent"
NODE_NAME = "Validate data shape"
NODE_TYPE = "recipe-step"
CLASSIFICATION = "gigo"
SCHEMA_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[2]

STR, NUM, BOOL, LIST, DATE, TIME = "string", "number", "boolean", "list", "date", "datetime"
# field: (type, required, nullable, extra)   extra: {"enum": [...]} | {"min": a, "max": b} | {"items": STR}
CONTRACT: dict[str, dict[str, tuple]] = {
    "guidance-signals": {
        "id": (STR, True, False, {}), "claim_id": (STR, True, False, {}), "earnings_call_id": (STR, True, False, {}),
        "ticker": (STR, True, False, {}), "company_name": (STR, False, True, {}), "call_date": (DATE, True, False, {}),
        "fiscal_quarter": (STR, False, True, {}), "guidance_topic": (STR, False, True, {}),
        "direction": (STR, True, False, {"enum": ["strengthened", "weakened", "unchanged"]}),
        "direction_confidence": (NUM, True, False, {"min": 0, "max": 1}), "claim_text": (STR, True, False, {}),
        "claim_summary": (STR, False, True, {}), "transcript_citation": (STR, False, True, {}),
        "change_description": (STR, False, True, {}), "metric_type": (STR, False, True, {}),
        "quantified_value": (NUM, False, True, {}), "metric_value_prior": (NUM, False, True, {}),
        "falsification_flag": (BOOL, False, True, {}), "schema_valid": (BOOL, True, False, {})},
    "risk-admissions": {
        "id": (STR, True, False, {}), "claim_id": (STR, True, False, {}), "earnings_call_id": (STR, True, False, {}),
        "ticker": (STR, True, False, {}), "call_date": (DATE, True, False, {}), "fiscal_quarter": (STR, False, True, {}),
        "risk_category": (STR, True, False, {}),
        "severity": (STR, True, False, {"enum": ["low", "medium", "high", "critical"]}),
        "risk_description": (STR, True, False, {}), "risk_summary": (STR, False, True, {}),
        "uncertainty_language": (STR, False, True, {}), "transcript_citation": (STR, False, True, {}),
        "prior_disclosure_call": (STR, False, True, {}), "schema_valid": (BOOL, True, False, {})},
    "qa-pressure-map": {
        "id": (STR, True, False, {}), "earnings_call_id": (STR, True, False, {}), "ticker": (STR, True, False, {}),
        "call_date": (DATE, True, False, {}), "fiscal_quarter": (STR, False, True, {}),
        "question_topic": (STR, True, False, {}), "question_text": (STR, False, True, {}),
        "response_type": (STR, False, True, {}), "response_summary": (STR, False, True, {}),
        "pressure_score": (NUM, True, False, {}), "analyst_firm": (LIST, False, True, {"items": STR}),
        "evasion_flag": (BOOL, True, False, {}), "times_asked": (NUM, False, True, {}),
        "schema_valid": (BOOL, True, False, {})},
    "news-signals": {
        "id": (STR, True, False, {}), "claim_id": (STR, True, False, {}), "ticker": (STR, True, False, {}),
        "published_at": (TIME, True, False, {}), "source_name": (STR, False, True, {}), "headline": (STR, True, False, {}),
        "sentiment_label": (STR, True, False, {"enum": ["positive", "negative", "neutral"]}),
        "sentiment_score": (NUM, True, False, {"min": -1, "max": 1}),
        "topic_tags": (LIST, True, False, {"items": STR}), "schema_valid": (BOOL, True, False, {})},
    "tech-stack-signals": {
        "id": (STR, True, False, {}), "claim_id": (STR, False, True, {}), "ticker": (STR, True, False, {}),
        "snapshot_date": (DATE, True, False, {}), "burst_detected": (BOOL, True, False, {}),
        "burst_ratio": (NUM, False, True, {}), "velocity_anomaly": (BOOL, True, False, {}),
        "velocity_z_score": (NUM, False, True, {}), "ai_focus_increasing": (BOOL, False, True, {}),
        "rising_languages": (LIST, False, True, {"items": STR}), "declining_languages": (LIST, True, False, {"items": STR}),
        "emerging_languages": (LIST, True, False, {"items": STR}), "stale_repo_count": (NUM, True, False, {"min": 0}),
        "schema_valid": (BOOL, True, False, {})},
}


def type_ok(v: Any, t: str) -> bool:
    if t == NUM:
        return isinstance(v, (int, float)) and not isinstance(v, bool)  # JSON true is not a number
    if t == BOOL:
        return isinstance(v, bool)
    if t == LIST:
        return isinstance(v, list)
    if t in (STR, DATE, TIME):
        if not isinstance(v, str):
            return False
        if t == DATE:
            return len(v) == 10 and v[4] == "-" and v[7] == "-" and v.replace("-", "").isdigit()
        if t == TIME:
            from datetime import datetime
            try:
                datetime.fromisoformat(v.replace("Z", "+00:00"))
                return True
            except ValueError:
                return False
    return True


def check_row(row: Any, contract: dict) -> list[dict]:
    if not isinstance(row, dict):
        return [{"field": None, "problem": "row_not_object", "value": repr(row)[:80]}]
    out = []
    for field, (t, required, nullable, extra) in contract.items():
        if field not in row or row[field] is None:
            if required or (field in row and not nullable):
                out.append({"field": field, "problem": "missing_required" if required else "null_not_allowed"})
            continue
        v = row[field]
        if not type_ok(v, t):
            out.append({"field": field, "problem": "type_error", "expected": t, "got": type(v).__name__, "value": repr(v)[:80]})
            continue
        if "enum" in extra and v not in extra["enum"]:
            out.append({"field": field, "problem": "not_in_allowed_set", "allowed": extra["enum"], "value": v})
        if t == NUM and (("min" in extra and v < extra["min"]) or ("max" in extra and v > extra["max"])):
            out.append({"field": field, "problem": "out_of_bounds", "min": extra.get("min"), "max": extra.get("max"), "value": v})
        if t == LIST and "items" in extra and not all(type_ok(x, extra["items"]) for x in v):
            out.append({"field": field, "problem": "list_item_type_error", "expected_items": extra["items"]})
    return out


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
    raw_dir = ROOT / f"data/raw/{WORKFLOW_SLUG}/runs/{run}"
    out_dir = ROOT / f"data/verified/{WORKFLOW_SLUG}/runs/{run}"
    sources, stops = [], []
    for source, contract in CONTRACT.items():
        p = raw_dir / f"{source}.json"
        rep = {"source_name": source, "schema_version": SCHEMA_VERSION, "parse_errors": [], "row_findings": []}
        if not p.exists():
            rep["parse_errors"].append("raw envelope missing (step 2 did not deliver it)")
        else:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not raw.get("parsed"):
                rep["parse_errors"] += raw.get("errors") or ["source did not parse"]
            elif not isinstance(raw.get("records"), list):
                rep["parse_errors"] += raw.get("errors") or ["no records list"]
            else:
                rows = raw["records"]
                clean = []
                for i, row in enumerate(rows):
                    f = check_row(row, contract)
                    if f:
                        rep["row_findings"].append({"index": i, "id": row.get("id") if isinstance(row, dict) else None,
                                                    "findings": f})
                    else:
                        clean.append(row)
                write_json(out_dir / f"{source}.json", {"source_name": source, "run": run, "schema_version": SCHEMA_VERSION,
                                                        "validated_at": env["frozen_clock"], "record_count": len(clean),
                                                        "records": clean, "withheld_count": len(rows) - len(clean)})
                rep.update(record_count=len(rows), promoted=len(clean), withheld=len(rows) - len(clean))
        rep["missing_fields"] = sorted({x["field"] for r in rep["row_findings"] for x in r["findings"]
                                        if x["problem"] == "missing_required"})
        rep["type_errors"] = sum(1 for r in rep["row_findings"] for x in r["findings"] if x["problem"] != "missing_required")
        rep["required_fields_present"] = not rep["missing_fields"] and not rep["parse_errors"]
        if rep["parse_errors"] or rep["row_findings"]:
            stops.append(f"{source}: {len(rep['parse_errors'])} parse error(s), {len(rep['row_findings'])} row(s) with shape findings")
        sources.append(rep)
    emit({"workflow": WORKFLOW_NAME, "node": NODE_NAME, "node_type": NODE_TYPE, "classification": CLASSIFICATION,
          "run": run, "schema_version": SCHEMA_VERSION, "sources": sources, "status": "stop" if stops else "ok",
          "stop_conditions": stops, "live_call_performed": False, "network_access": "none",
          "next_step": None if stops else "transform-quality-check",
          "human_gate": {"gate": 3, "capacity": "[PA]", "cleared_by": None,
                         "note": "Gate 3: every raw and verified JSON output parses and every shape finding has been read."}},
         a.output)
    return 1 if stops else 0


if __name__ == "__main__":
    raise SystemExit(main())
