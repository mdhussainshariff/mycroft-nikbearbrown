"""Purpose: Prove the recipe's detection step does exactly what the ORIGINAL n8n workflow does, by running the original JavaScript and comparing.
Input: the original workflow JSON (its `Aggregate All Signals` and `Run Pattern Detection Engine` code nodes), the frozen sample corpus, and expected-flags.json.
Output: a JSON parity report (per company: expected vs original-JS vs Python-port flags and summaries) on stdout and optionally --output.
Side effects: runs `node` on a temporary harness; writes only the optional --output file. No network.
Idempotent: Yes; the clock is frozen to the corpus's frozen_clock in both engines.
Recipe: recipes/contradiction-detection-agent.md

Why this exists: a port is only trustworthy if it can be shown to behave like its source. The original
JavaScript is extracted from the workflow JSON at run time (never copied into this file), executed
under a minimal shim for n8n's `$input` / `$(node)` accessors, and compared field by field with the
expectations written before any port existed, and with the Python port (step 5) once present.

Exit codes: 0 = every company agrees on every compared field; 1 = any disagreement (the report says
which); 2 = cannot run (node missing, source JSON missing or unparseable).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Importing the step scripts must not leave __pycache__ folders in the repo's shared scripts/ directories.
sys.dont_write_bytecode = True

WORKFLOW_SLUG = "contradiction-detection-agent"
ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "data/mycroft-main/n8n-workflows/originals/n8n_Workflows/Contradiction_Detection_Agent/Contradiction_detection_agent.json"
SAMPLE = ROOT / f"data/raw/{WORKFLOW_SLUG}/sample"
SOURCES = ["guidance-signals", "risk-admissions", "qa-pressure-map", "news-signals", "tech-stack-signals"]

HARNESS = r"""
const fs = require('fs');
const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const code = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const RealDate = Date;
const FROZEN = job.frozen_clock;
global.Date = class extends RealDate {                       // freeze the clock for both nodes
  constructor(...a) { super(...(a.length ? a : [FROZEN])); }
  static now() { return new RealDate(FROZEN).getTime(); }
};
function run(src, inputJson, nodeOutputs) {
  const $input = { first: () => ({ json: inputJson }), all: () => [{ json: inputJson }] };
  const $ = (name) => ({
    first: () => ({ json: name === 'Set Company Input' ? job.ctx : (nodeOutputs[name] || [])[0] }),
    all:   () => (nodeOutputs[name] || []).map(r => ({ json: r })),
  });
  return (new Function('$input', '$', src))($input, $)[0].json;
}
const agg = run(code.aggregate, {}, job.node_rows);
const out = run(code.engine, agg, {});
process.stdout.write(JSON.stringify(out));
"""


def load_step(name: str):
    """Import a recipe step script by path (its file name has hyphens)."""
    path = ROOT / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def original_code() -> dict:
    wf = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    nodes = {n["name"]: n.get("parameters", {}).get("jsCode", "") for n in wf["nodes"]}
    return {"aggregate": nodes["Aggregate All Signals"], "engine": nodes["Run Pattern Detection Engine"]}


def comparable(out: dict) -> dict:
    return {"flags": [{k: f.get(k) for k in ("flag_id", "pattern_id", "pattern_name", "severity", "conflict_description",
                                             "claim_a_id", "claim_b_id", "evidence_for_a", "evidence_for_b")}
                      for f in out.get("contradiction_flags", [])],
            "detection_summary": out.get("detection_summary"),
            "skipped_patterns": out.get("skipped_patterns")}


def load_python_port():
    path = ROOT / f"scripts/tools/{WORKFLOW_SLUG}-run-approved-tools.py"
    return load_step(str(path.relative_to(ROOT))) if path.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture-set", default="clean")
    ap.add_argument("--output")
    a = ap.parse_args()
    node = shutil.which("node")
    if not node or not ORIGINAL.exists():
        print(json.dumps({"status": "stop", "reason": "node missing" if not node else f"missing {ORIGINAL}"}))
        return 2
    expected = json.loads((SAMPLE / "expected-flags.json").read_text(encoding="utf-8"))
    tables = {s: json.loads((SAMPLE / a.fixture_set / f"{s}.json").read_text(encoding="utf-8"))["rows"] for s in SOURCES}
    code = original_code()
    port = load_python_port()
    # Selection and company context come from step 4 itself, so this test exercises the pipeline's own
    # reproduction of the original queries rather than a private copy of it.
    step4 = load_step(f"scripts/gigo/{WORKFLOW_SLUG}-transform-quality-check.py")
    env = {"frozen_clock": expected["frozen_clock"], "lookback_days": 365, "active_patterns": [1, 2, 3, 4, 5, 6]}
    report, all_ok = [], True
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "code.json").write_text(json.dumps(code), encoding="utf-8")
        (Path(tmp) / "h.js").write_text(HARNESS, encoding="utf-8")
        for sc in expected["scenarios"]:
            t = sc["ticker"]
            selected = {s: step4.select_like_original_sql(tables[s], s, t)[0] for s in SOURCES}
            node_rows = {step4.ORIGINAL_QUERY[s][0]: selected[s] for s in SOURCES}
            job = {"frozen_clock": expected["frozen_clock"],
                   "ctx": step4.ctx_for({"ticker": t, "company_name": sc["company_name"]}, env), "node_rows": node_rows}
            (Path(tmp) / "job.json").write_text(json.dumps(job), encoding="utf-8")
            r = subprocess.run([node, str(Path(tmp) / "h.js"), str(Path(tmp) / "job.json"), str(Path(tmp) / "code.json")],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(json.dumps({"status": "stop", "ticker": t, "node_error": r.stderr[-800:]}))
                return 2
            js = comparable(json.loads(r.stdout))
            got = [{"pattern_id": f["pattern_id"], "severity": f["severity"], "claim_a_id": f["claim_a_id"],
                    "claim_b_id": f["claim_b_id"]} for f in js["flags"]]
            exp_vs_js = (got == sc["expected_flags"]
                         and js["detection_summary"]["overall_confidence_level"] == sc["expected_overall_confidence_level"]
                         and [{"pattern_id": p["pattern_id"], "reason": p["reason"]} for p in js["skipped_patterns"]]
                         == sc["expected_skipped_patterns"])
            row = {"ticker": t, "purpose": sc["purpose"], "expected_matches_original_js": exp_vs_js,
                   "original_js": js}
            if port is not None:
                py = comparable(port.detect(port.aggregate(job["ctx"], selected)))
                row["python_port"] = py
                row["python_matches_original_js"] = (py == js)
            ok = exp_vs_js and row.get("python_matches_original_js", True)
            all_ok &= ok
            row["status"] = "agree" if ok else "DISAGREE"
            report.append(row)
    out = {"workflow": WORKFLOW_SLUG, "fixture_set": a.fixture_set, "original_source": str(ORIGINAL.relative_to(ROOT)),
           "python_port_present": port is not None, "companies": len(report),
           "agree": sum(r["status"] == "agree" for r in report), "results": report,
           "network_access": "none", "live_call_performed": False}
    text = json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False)
    if a.output:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        with open(a.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    print(text)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
