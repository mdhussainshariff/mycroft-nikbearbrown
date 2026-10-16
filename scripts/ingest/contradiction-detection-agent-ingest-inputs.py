"""Purpose: Ingest the recipe's five declared signal sources into the raw layer, transporting them exactly as received.
Input: data/raw/contradiction-detection-agent/run-envelope.json and the fixture set it names (sample mode); --fixture-set overrides the set for one run.
Output: one raw envelope per source under data/raw/contradiction-detection-agent/runs/<run_id>-<fixture_set>/<source>.json, plus a step summary on stdout (and --output).
Side effects: writes into data/raw/ only. No network in sample mode; live mode is not implemented and stops before any connection.
Idempotent: Yes; fetched_at comes from the envelope's frozen_clock, never from now().
Recipe: recipes/contradiction-detection-agent.md

Transport, don't repair. This step answers one question: did each declared source arrive, and what
exactly did it contain? It doesn't drop, dedupe, coerce, filter by ticker or sort. Those are judgments for
steps 3 and 4, which report them. A file that doesn't parse is carried through byte for byte (with
`parsed: false`) so step 3 can report it, rather than disappearing here.

Live mode. The original workflow reads five Postgres tables and the Alpha Vantage news API. Live
ingest would need DATABASE_URL and ALPHA_VANTAGE_API_KEY from the environment and a gate-5 approval
record naming a human. It is deliberately unimplemented: live mode stops, naming what it would need.

Layer contract: ingest is the only layer allowed to touch the network (P2); in sample mode it doesn't.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

WORKFLOW_NAME = "Contradiction_detection_agent"
WORKFLOW_SLUG = "contradiction-detection-agent"
NODE_NAME = "Ingest declared inputs"
NODE_TYPE = "recipe-step"
CLASSIFICATION = "ingest"
ROOT = Path(__file__).resolve().parents[2]
REQUIRED_ENVELOPE = ("run_id", "mode", "fixture_set", "frozen_clock", "fixture_root", "sources", "companies")
# What each source stands for in the original workflow (for provenance, not for fetching).
ORIGINAL_NODE = {"guidance-signals": "DB: Fetch Earnings Guidance Signals", "risk-admissions": "DB: Fetch Risk Admissions",
                 "qa-pressure-map": "DB: Fetch QA Pressure Map", "news-signals": "DB: Fetch News Signals",
                 "tech-stack-signals": "DB: Fetch Tech Stack Signals"}


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
    env_path = Path(a.envelope)
    base = {"workflow": WORKFLOW_NAME, "node": NODE_NAME, "node_type": NODE_TYPE, "classification": CLASSIFICATION,
            "live_call_performed": False, "network_access": "none",
            "human_gate": {"gate": 2, "capacity": "[PF]", "cleared_by": None,
                           "note": "Gate 2 confirms the envelope declares sample mode (or an approved live mode) before ingest."}}
    if not env_path.exists():
        emit({**base, "status": "stop", "stop_conditions": [f"run envelope missing: {env_path}"], "next_step": None}, a.output)
        return 1
    env = json.loads(env_path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_ENVELOPE if k not in env]
    if missing:
        emit({**base, "status": "stop", "stop_conditions": [f"run envelope lacks {missing}"], "next_step": None}, a.output)
        return 1
    if env["mode"] != "sample":
        need = env.get("live_mode_requirements", {})
        emit({**base, "status": "stop", "next_step": None, "stop_conditions": [
            f"mode '{env['mode']}' requested: live ingest is not implemented. It would need {need.get('credentials')} "
            f"from the environment and an approval record at {need.get('approval_record_path')} naming a human."]}, a.output)
        return 1
    fixture_set = a.fixture_set or env["fixture_set"]
    run = f"{env['run_id']}-{fixture_set}"
    src_dir = ROOT / env["fixture_root"] / fixture_set
    out_dir = ROOT / f"data/raw/{WORKFLOW_SLUG}/runs/{run}"
    stops, per = [], []
    for source in env["sources"]:
        candidates = [src_dir / f"{source}.json", src_dir / f"{source}.json.broken"]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            stops.append(f"declared source '{source}' has no file in {src_dir.relative_to(ROOT)}")
            per.append({"source_name": source, "arrived": False})
            continue
        raw = path.read_bytes()
        record = {"source_name": source, "source_type": "fixture", "original_node": ORIGINAL_NODE.get(source),
                  "source_url_or_path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(),
                  "fetched_at": env["frozen_clock"], "sample_mode": True, "run": run, "rejects": [], "errors": []}
        try:
            body = json.loads(raw.decode("utf-8"))
            rows = body.get("rows") if isinstance(body, dict) else None
            if not isinstance(rows, list):
                record.update(parsed=True, records=None, record_count=None,
                              errors=["top-level 'rows' list absent; carried for step 3 to report"], raw_body=body)
            else:
                record.update(parsed=True, records=rows, record_count=len(rows))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            # carried, not dropped: step 3 owns reporting it (transport, don't repair)
            record.update(parsed=False, records=None, record_count=None, errors=[f"does not parse: {e}"],
                          raw_text=raw.decode("utf-8", errors="replace"))
        write_json(out_dir / f"{source}.json", record)
        per.append({"source_name": source, "arrived": True, "parsed": record["parsed"], "original_node": ORIGINAL_NODE.get(source),
                    "record_count": record["record_count"], "path": str((out_dir / f"{source}.json").relative_to(ROOT))})
    emit({**base, "status": "stop" if stops else "ok", "stop_conditions": stops, "run": run, "mode": env["mode"],
          "fixture_set": fixture_set, "sources": per, "fetched_at": env["frozen_clock"],
          "records": sum(p.get("record_count") or 0 for p in per),
          "next_step": None if stops else "validate-data-shape"}, a.output)
    return 1 if stops else 0


if __name__ == "__main__":
    raise SystemExit(main())
