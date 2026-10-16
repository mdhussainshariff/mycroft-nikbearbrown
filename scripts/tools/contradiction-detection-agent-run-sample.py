"""Purpose: Run the recipe's six steps in order over one fixture set, saving each step's report where step 6 reads it.
Input: --fixture-set clean|defective (default: the envelope's) and the run envelope.
Output: logs/contradiction-detection-agent/runs/<run>/step-<n>-<step>.json for each step run, then step 6's artifacts; a one-line status per step on stdout.
Side effects: only those of the six steps it runs. No network.
Idempotent: Yes, as each step is.
Recipe: recipes/contradiction-detection-agent.md

Dialogic, not silent. This is a convenience for sample runs: it runs a step only if the previous one
finished with status "ok", and it never clears a gate. A step that stops halts the processing steps, but
step 6 still runs so the stop is documented in the report and audit instead of vanishing. Exit status is
the first non-zero step's, so a halted run never looks like a passing one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

WORKFLOW_SLUG = "contradiction-detection-agent"
ROOT = Path(__file__).resolve().parents[2]
STEPS = [("tools", "verify-provenance"), ("ingest", "ingest-inputs"), ("gigo", "validate-data-shape"),
         ("gigo", "transform-quality-check"), ("tools", "run-approved-tools")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture-set", choices=["clean", "defective"])
    ap.add_argument("--envelope", default=str(ROOT / f"data/raw/{WORKFLOW_SLUG}/run-envelope.json"))
    a = ap.parse_args()
    env = json.loads(Path(a.envelope).read_text(encoding="utf-8"))
    fset = a.fixture_set or env["fixture_set"]
    run = f"{env['run_id']}-{fset}"
    logdir = ROOT / f"logs/{WORKFLOW_SLUG}/runs/{run}"
    for old in logdir.glob("step-*.json"):  # a rerun must not report a previous run's steps
        old.unlink()
    first_fail = 0
    for n, (layer, step) in enumerate(STEPS, 1):
        cmd = [sys.executable, str(ROOT / f"scripts/{layer}/{WORKFLOW_SLUG}-{step}.py"), "--envelope", a.envelope,
               "--output", str(logdir / f"step-{n}-{step}.json")]
        if step != "verify-provenance":
            cmd[2:2] = ["--fixture-set", fset]
        r = subprocess.run(cmd, capture_output=True, text=True)
        status = json.loads(r.stdout).get("status") if r.stdout.strip().startswith("{") else "error"
        print(f"step {n} {step}: exit {r.returncode}, status {status}")
        if r.returncode != 0:
            first_fail = first_fail or r.returncode
            print(f"  halted: later processing steps are not run; step 6 documents the stop")
            break
    r = subprocess.run([sys.executable, str(ROOT / f"scripts/tools/{WORKFLOW_SLUG}-produce-human-report.py"),
                        "--envelope", a.envelope, "--fixture-set", fset,
                        "--output", str(logdir / "step-6-produce-human-report.json")], capture_output=True, text=True)
    out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    print(f"step 6 produce-human-report: exit {r.returncode} · {out.get('summary')} · report {out.get('outputs', {}).get('report')}")
    return first_fail or r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
