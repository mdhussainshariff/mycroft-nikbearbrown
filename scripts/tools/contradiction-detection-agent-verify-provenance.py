"""Purpose: Before anything runs, confirm that every declared source of this recipe exists, parses, and is the one the recipe says it is.
Input: the recipe, the original n8n workflow JSON, the sample corpus (fixture manifest, expected flags), the run envelope, and any gate-decision records.
Output: workflow, source_paths, exists, parsed_ok, approval_state, checked_at, findings_digest (and per-source detail) on stdout and in logs/contradiction-detection-agent/runs/<run>/step-1-verify-provenance.json when --output is given.
Side effects: none except the optional --output file. Reads only local files; no network.
Idempotent: Yes; checked_at comes from the envelope's frozen_clock, and findings_digest hashes the findings, not the time.
Recipe: recipes/contradiction-detection-agent.md

What "is the one the recipe says it is" means here. The recipe's node table lists the 26 nodes of the
original workflow by name and type. This step reads the workflow JSON and requires the same set: a
renamed, missing or extra node means the recipe no longer describes its source, and the run stops (P3).

approval_state reads the gate-5 record (logs/gate-decisions/contradiction-detection-agent-gate-5.json)
when it exists. It reports `approved_for_live_action` exactly as recorded and never infers it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

WORKFLOW_NAME = "Contradiction_detection_agent"
WORKFLOW_SLUG = "contradiction-detection-agent"
NODE_NAME = "Verify provenance"
NODE_TYPE = "recipe-step"
CLASSIFICATION = "tools"
ROOT = Path(__file__).resolve().parents[2]
RECIPE = f"recipes/{WORKFLOW_SLUG}.md"
ORIGINAL = "data/mycroft-main/n8n-workflows/originals/n8n_Workflows/Contradiction_Detection_Agent/Contradiction_detection_agent.json"
SAMPLE = f"data/raw/{WORKFLOW_SLUG}/sample"
GATE5 = f"logs/gate-decisions/{WORKFLOW_SLUG}-gate-5.json"


def check_json(rel: str) -> dict:
    p = ROOT / rel
    d = {"path": rel, "exists": p.exists(), "parsed_ok": False}
    if p.exists():
        raw = p.read_bytes()
        d["sha256"] = hashlib.sha256(raw).hexdigest()
        try:
            d["_data"] = json.loads(raw.decode("utf-8"))
            d["parsed_ok"] = True
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            d["error"] = f"does not parse: {e}"
    return d


def recipe_node_table(text: str) -> dict[str, str]:
    """The recipe's '| Node Name | Node Type | Classification |' table: {name: n8n type}."""
    out, on = {}, False
    for line in text.splitlines():
        if line.startswith("| Node Name | Node Type |"):
            on = True
            continue
        if on:
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells[0].startswith("---"):
                continue
            out[cells[0]] = cells[1].strip("`")
    return out


def emit(data: Any, output: str | None) -> None:
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    print(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--envelope", default=str(ROOT / f"data/raw/{WORKFLOW_SLUG}/run-envelope.json"))
    ap.add_argument("--output")
    a = ap.parse_args()
    findings, stops = [], []
    try:
        env_rel = str(Path(a.envelope).resolve().relative_to(ROOT))
    except ValueError:  # an envelope outside the repo is still checked, by its given path
        env_rel = a.envelope
    checks = {"run_envelope": check_json(env_rel), "original_workflow": check_json(ORIGINAL),
              "fixture_manifest": check_json(f"{SAMPLE}/fixture-manifest.json"),
              "expected_flags": check_json(f"{SAMPLE}/expected-flags.json")}
    recipe_p = ROOT / RECIPE
    checks["recipe"] = {"path": RECIPE, "exists": recipe_p.exists(), "parsed_ok": recipe_p.exists()}
    for name, c in checks.items():
        if not c["exists"]:
            stops.append(f"{name} missing: {c['path']}")
        elif not c["parsed_ok"]:
            stops.append(f"{name} does not parse: {c['path']}")
    env = checks["run_envelope"].get("_data") or {}
    if env and env.get("mode") not in ("sample", "live"):
        stops.append(f"run envelope declares an unknown mode: {env.get('mode')!r}")
    # the recipe must describe the workflow it ports: same node names and types
    wf = checks["original_workflow"].get("_data")
    if wf and recipe_p.exists():
        actual = {n["name"]: n["type"].split(".")[-1] for n in wf.get("nodes", [])}
        declared = recipe_node_table(recipe_p.read_text(encoding="utf-8"))
        missing = sorted(set(declared) - set(actual))
        extra = sorted(set(actual) - set(declared))
        retyped = sorted(n for n in set(actual) & set(declared) if actual[n] != declared[n])
        checks["original_workflow"].update(node_count=len(actual), declared_in_recipe=len(declared),
                                           title_matches_pipeline=bool(re.search(r"contradiction", wf.get("name", ""), re.I))
                                           if wf.get("name") else None)
        for label, names in (("in recipe but not in workflow", missing), ("in workflow but not in recipe", extra),
                             ("type differs", retyped)):
            if names:
                stops.append(f"node table mismatch ({label}): {names}")
    # declared fixture files exist and are hashed
    man = checks["fixture_manifest"].get("_data") or {}
    for f in man.get("files", []):
        p = ROOT / f["path"]
        if not p.exists():
            stops.append(f"fixture named by the manifest is missing: {f['path']}")
        elif f.get("sha256") and hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
            stops.append(f"fixture changed since the manifest froze it: {f['path']}")
    gate5 = check_json(GATE5)
    approval = {"record": GATE5, "exists": gate5["exists"],
                "approved_for_live_action": (gate5.get("_data") or {}).get("approved_for_live_action", False)
                if gate5["parsed_ok"] else False}
    findings = sorted(stops)
    for c in checks.values():
        c.pop("_data", None)
    result = {"workflow": WORKFLOW_NAME, "node": NODE_NAME, "node_type": NODE_TYPE, "classification": CLASSIFICATION,
              "source_paths": {k: v["path"] for k, v in checks.items()},
              "exists": {k: v["exists"] for k, v in checks.items()},
              "parsed_ok": {k: v["parsed_ok"] for k, v in checks.items()}, "detail": checks,
              "approval_state": approval, "checked_at": env.get("frozen_clock"),
              "findings_digest": hashlib.sha256(json.dumps(findings).encode()).hexdigest()[:16],
              "status": "stop" if stops else "ok", "stop_conditions": stops, "live_call_performed": False,
              "network_access": "none", "next_step": None if stops else "ingest-inputs",
              "human_gate": {"gate": 1, "capacity": "[TO]", "cleared_by": None,
                             "note": "Gate 1: a human confirms the sources are the intended ones before ingest."}}
    emit(result, a.output)
    return 1 if stops else 0


if __name__ == "__main__":
    raise SystemExit(main())
