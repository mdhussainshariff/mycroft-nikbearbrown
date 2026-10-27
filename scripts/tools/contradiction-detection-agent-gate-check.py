"""Purpose: The recipe's six phase-gate tests, each with a real failure path: a gate passes only when its handoff condition is demonstrably met.
Input: --gate 1..6 and --run (default: the envelope's run_id with the clean fixture set); reads the run's step reports, outputs, the envelope, the recipe's six step scripts, and gate-decision records.
Output: one JSON line {gate, name, passed, checks[], reason} on stdout. Exit 0 = condition met, 1 = not met, 2 = unknown gate.
Side effects: none (gate 4 runs the parity check, which itself writes nothing).
Idempotent: Yes.
Recipe: recipes/contradiction-detection-agent.md

Why a script, not a one-liner. P4 asks every gate to have a real failure path, and a script makes that
easy to show: each check is stated as a condition, reports which part failed, and is break-tested by the
self-test, which runs every gate against an empty tree and requires it to fail.

A passing test is necessary, not sufficient: clearing a gate is still a recorded decision by a named
human (logs/gate-decisions/), which this script never writes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

WORKFLOW_SLUG = "contradiction-detection-agent"
ROOT = Path(__file__).resolve().parents[2]
ENVELOPE = ROOT / f"data/raw/{WORKFLOW_SLUG}/run-envelope.json"
STEP_SCRIPTS = ["tools/verify-provenance", "ingest/ingest-inputs", "gigo/validate-data-shape",
                "gigo/transform-quality-check", "tools/run-approved-tools", "tools/produce-human-report"]
REPORT_SECTIONS = ["Run summary", "Purpose", "Source inventory", "Inputs used", "Phase-gate results", "Steps completed",
                   "Records seen", "Rejects", "Duplicates", "Flags", "Typed TODOs", "Human approvals",
                   "Verified findings", "Inferred findings", "Decision recommendation"]
LOG_FIELDS = ["workflow", "run_id", "mode", "steps_completed", "records_seen", "rejects", "duplicates", "flags",
              "stop_conditions", "todo_items", "source_files", "gate_decisions", "generated_at", "raw_output_paths",
              "verified_output_paths", "report_path"]
NAMES = {1: "Source gate", 2: "Scope gate", 3: "Data-shape gate", 4: "Script-readiness gate", 5: "Approval gate", 6: "Report gate"}


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def script(rel: str) -> Path:
    layer, step = rel.split("/")
    return ROOT / f"scripts/{layer}/{WORKFLOW_SLUG}-{step}.py"


def gate(n: int, run: str) -> list[tuple[str, bool]]:
    logdir = ROOT / f"logs/{WORKFLOW_SLUG}/runs/{run}"
    env = load(ENVELOPE)
    if n == 1:
        rep = load(logdir / "step-1-verify-provenance.json")
        checks = [("step-1 report for this run exists", rep is not None),
                  ("step 1 reported status ok", bool(rep) and rep.get("status") == "ok")]
        fresh = subprocess.run([sys.executable, str(script("tools/verify-provenance"))], capture_output=True, text=True)
        now = load_text(fresh.stdout)
        checks += [("a fresh provenance check passes now", fresh.returncode == 0),
                   ("no drift since the run (findings digest unchanged)",
                    bool(rep and now) and rep.get("findings_digest") == now.get("findings_digest"))]
        return checks
    if n == 2:
        g5 = load(ROOT / f"logs/gate-decisions/{WORKFLOW_SLUG}-gate-5.json") or {}
        mode = (env or {}).get("mode")
        return [("run envelope parses", env is not None),
                ("mode is sample, or live with a gate-5 approve record",
                 mode == "sample" or (mode == "live" and g5.get("decision") == "approve" and g5.get("approved_for_live_action") is True)),
                ("a fixture set is declared", bool((env or {}).get("fixture_set"))),
                ("companies are declared, not inferred", bool((env or {}).get("companies")))]
    if n == 3:
        files = [p for d in (ROOT / f"data/raw/{WORKFLOW_SLUG}/runs/{run}", ROOT / f"data/verified/{WORKFLOW_SLUG}/runs/{run}")
                 if d.exists() for p in d.rglob("*.json")]
        bad = [str(p.relative_to(ROOT)) for p in files if load(p) is None]
        rep = load(logdir / "step-3-validate-data-shape.json")
        return [("this run has raw and verified JSON outputs", len(files) > 0),
                (f"every output parses ({len(files)} files; failing: {bad[:3]})", len(files) > 0 and not bad),
                ("step 3 reported status ok", bool(rep) and rep.get("status") == "ok")]
    if n == 4:
        checks = []
        for s in STEP_SCRIPTS:
            p = script(s)
            ok = p.exists()
            if ok:
                try:  # syntax-compile in memory: a readiness check must not write .pyc files into the repo
                    compile(p.read_text(encoding="utf-8"), str(p), "exec")
                except SyntaxError:
                    ok = False
            checks.append((f"{p.name} exists and compiles", ok))
        par = ROOT / f"scripts/tools/{WORKFLOW_SLUG}-parity-check.py"
        r = subprocess.run([sys.executable, str(par)], capture_output=True, text=True) if par.exists() else None
        checks.append(("the detector matches the original workflow's JavaScript (parity check exit 0)", bool(r) and r.returncode == 0))
        return checks
    if n == 5:
        rec = load(ROOT / f"logs/gate-decisions/{WORKFLOW_SLUG}-gate-5.json")
        live = [str(p.relative_to(ROOT)) for d in (ROOT / f"logs/{WORKFLOW_SLUG}", ROOT / f"data/raw/{WORKFLOW_SLUG}/runs")
                if d.exists() for p in d.rglob("*.json") if '"live_call_performed": true' in p.read_text(encoding="utf-8")]
        decided = bool(rec) and rec.get("decision") in ("approve", "deny") and bool((rec.get("decided_by") or {}).get("name"))
        return [("a gate-5 decision record exists and parses", rec is not None),
                ("it names a human and records approve or deny", decided),
                (f"no artifact records a live call unless that decision approved it (live calls found: {live[:3]})",
                 not live or (decided and rec.get("decision") == "approve" and rec.get("approved_for_live_action") is True))]
    if n == 6:
        date = (env or {}).get("frozen_clock", "")[:10]
        fset = run.rsplit("-", 1)[-1]
        rep_p = ROOT / f"reports/generated/{WORKFLOW_SLUG}-{date}-{fset}.md"
        log = load(ROOT / f"logs/{WORKFLOW_SLUG}-{date}-{fset}.json")
        text = rep_p.read_text(encoding="utf-8") if rep_p.exists() else ""
        missing_s = [s for s in REPORT_SECTIONS if f"## {s}" not in text]
        missing_f = [f for f in LOG_FIELDS if not log or f not in log]
        return [("human report exists", rep_p.exists()),
                (f"report has every contract section (missing: {missing_s})", rep_p.exists() and not missing_s),
                ("Reader and Decision enabled are stated", "**Reader:**" in text and "**Decision enabled:**" in text),
                ("agent log exists", log is not None), (f"agent log has every contract field (missing: {missing_f})", not missing_f)]
    return []


def load_text(s: str):
    try:
        return json.loads(s)
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gate", type=int, required=True)
    ap.add_argument("--run")
    a = ap.parse_args()
    if a.gate not in NAMES:
        print(json.dumps({"gate": a.gate, "passed": False, "reason": "unknown gate"}))
        return 2
    env = load(ENVELOPE) or {}
    run = a.run or f"{env.get('run_id', 'sample-001')}-clean"
    checks = gate(a.gate, run)
    passed = bool(checks) and all(ok for _, ok in checks)
    print(json.dumps({"gate": a.gate, "name": NAMES[a.gate], "run": run, "passed": passed,
                      "checks": [{"condition": c, "met": ok} for c, ok in checks],
                      "reason": "all conditions met" if passed else "not met: " + "; ".join(c for c, ok in checks if not ok)},
                     sort_keys=True, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
