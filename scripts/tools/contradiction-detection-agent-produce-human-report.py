"""Purpose: Turn one sample run into the three artifacts the recipe's output contract names: a human report, an agent log, and an audit written beside the verified data.
Input: the step reports of one run (logs/contradiction-detection-agent/runs/<run>/step-<n>-*.json), step 5's detection results, the run envelope, the fixture manifest and expected flags, the recipe (for its typed TODOs) and any gate-decision records.
Output: reports/generated/contradiction-detection-agent-<DATE>-<set>.md, logs/contradiction-detection-agent-<DATE>-<set>.json and data/verified/contradiction-detection-agent/runs/<run>/<run>-audit.md (summary, sources_checked, gate_results, findings, typed_todos, next_decision on stdout).
Side effects: writes those three files only. No network.
Idempotent: Yes; <DATE> and every timestamp come from the envelope's frozen_clock.
Recipe: recipes/contradiction-detection-agent.md

Two readers, two artifacts (P5). The report is for the person who decides whether this run moves
forward: plain language, what was found, what was not, and the decision it enables. The agent log is
for the next machine step: the contract's fields, nothing interpretive.

Verified versus inferred. A detector flag is reported as what it is: "these two sources disagree on
this point". The report never upgrades a flag into a statement about the company ("they contradicted
themselves", "they evaded"). Where a flag's wording is easy to over-read, the report adds a short
reading note beside it (see the recipe's Notes from porting). Model judgments would be labelled as judgments, but
none exist: the LLM is never called in sample mode.

The audit says what it found. Records in and out at every step, every withheld row with its reason,
every kept-but-questionable row, and, for the sample corpus, expected versus actual. It does not
grade the run; the gates are for humans.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

WORKFLOW_NAME = "Contradiction_detection_agent"
WORKFLOW_SLUG = "contradiction-detection-agent"
NODE_NAME = "Produce human report"
NODE_TYPE = "recipe-step"
CLASSIFICATION = "tools"
ROOT = Path(__file__).resolve().parents[2]
STEPS = ["verify-provenance", "ingest-inputs", "validate-data-shape", "transform-quality-check",
         "run-approved-tools", "produce-human-report"]
GATES = ["Source gate", "Scope gate", "Data-shape gate", "Script-readiness gate", "Approval gate", "Report gate"]
# Reading notes shown beside a flag, so its wording isn't read as more than its inputs show (the recipe's Notes from porting).
def reading_note(f: dict, flags: list) -> str:
    out = []
    if f["pattern_id"] == 3:
        out.append("This pattern's input is a repeated topic or a pressure score of 7 or more, so 'evaded' "
                   "reads best as 'asked repeatedly or under pressure'.")
    if f["pattern_name"] == "Risk Admission vs News Coverage Gap":
        out.append("News is matched to a risk by comparing tag text, so the same topic written differently "
                   "(with a space instead of an underscore, say) doesn't match. Worth checking the coverage by hand.")
    if f["pattern_id"] == 6 and any(g["pattern_id"] == 1 and g["ticker"] == f["ticker"] and g["claim_a_id"] == f["claim_a_id"]
                                     for g in flags):
        out.append("The same guidance claim also raised a Pattern 1 flag, so these two flags describe one "
                   "disagreement.")
    return " ".join(out)


def load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--envelope", default=str(ROOT / f"data/raw/{WORKFLOW_SLUG}/run-envelope.json"))
    ap.add_argument("--fixture-set", choices=["clean", "defective"])
    ap.add_argument("--output")
    a = ap.parse_args()
    env = load(Path(a.envelope))
    if env is None:
        print(json.dumps({"status": "stop", "stop_conditions": ["run envelope missing"]}))
        return 1
    fset = a.fixture_set or env["fixture_set"]
    run = f"{env['run_id']}-{fset}"
    date = env["frozen_clock"][:10]
    logdir = ROOT / f"logs/{WORKFLOW_SLUG}/runs/{run}"
    steps = {s: load(logdir / f"step-{i + 1}-{s}.json") for i, s in enumerate(STEPS[:5])}
    det_dir = logdir / "detection"
    dets = [load(p) for p in sorted(det_dir.glob("*.json"))] if det_dir.exists() else []
    sample = ROOT / f"data/raw/{WORKFLOW_SLUG}/sample"
    expected = load(sample / "expected-flags.json") if fset == "clean" else None
    manifest = load(sample / "fixture-manifest.json")
    recipe_text = (ROOT / f"recipes/{WORKFLOW_SLUG}.md").read_text(encoding="utf-8")
    # A marker inside a code span is a quotation (e.g. an original gate test kept for the record), not an open item.
    spans = [m.span() for m in re.finditer(r"`[^`\n]*`", recipe_text)]
    todos = [m.group(0).strip() for m in re.finditer(r"\[TODO: [A-Z ]+\][^\n]{0,160}", recipe_text)
             if not any(a <= m.start() < b for a, b in spans)]
    gate_records = {i: load(ROOT / f"logs/gate-decisions/{WORKFLOW_SLUG}-gate-{i}.json") for i in range(1, 7)}

    completed = [s for s in STEPS[:5] if steps[s] and steps[s].get("status") == "ok"]
    stopped = [(s, steps[s].get("stop_conditions")) for s in STEPS[:5] if steps[s] and steps[s].get("status") == "stop"]
    not_run = [s for s in STEPS[:5] if steps[s] is None]
    s2, s3, s4, s5 = (steps[k] or {} for k in STEPS[1:5])
    records_seen = s2.get("records", 0)
    rejects = s4.get("rejects", [])
    duplicates = s4.get("duplicates", [])
    stale = s4.get("stale_rows", [])
    shape = [(src["source_name"], rf) for src in s3.get("sources", []) for rf in src.get("row_findings", [])]
    parse = [(src["source_name"], e) for src in s3.get("sources", []) for e in src.get("parse_errors", [])]
    flags = [f for d in dets for f in d["contradiction_flags"]]
    # One list of everything withheld, used by both the report and the agent log, so the two can't disagree.
    all_rejects = ([{"step": 3, "source": src, "id": None, "reason": f"unparseable source: {e}"} for src, e in parse]
                   + [{"step": 3, "source": src, "id": rf.get("id"),
                       "reason": "; ".join(x["problem"] + (f" on {x['field']}" if x.get("field") else "") for x in rf["findings"])}
                      for src, rf in shape]
                   + [{"step": 4, "source": r["source"], "id": r["id"], "reason": r["reason"]} for r in rejects])
    # What a stopped run never examined, said plainly rather than reported as zero.
    not_checked = [] if s4 else ["duplicates", "rows older than the declared lookback", "quality rejects"]

    # expected vs actual (sample corpus only)
    comparison = []
    if expected:
        got = {d["ticker"]: d for d in dets}
        for sc in expected["scenarios"]:
            d = got.get(sc["ticker"])
            actual = [{"pattern_id": f["pattern_id"], "severity": f["severity"], "claim_a_id": f["claim_a_id"],
                       "claim_b_id": f["claim_b_id"]} for f in (d["contradiction_flags"] if d else [])]
            level = d["detection_summary"]["overall_confidence_level"] if d else None
            comparison.append({"ticker": sc["ticker"], "expected_flags": len(sc["expected_flags"]), "actual_flags": len(actual),
                               "matches": d is not None and actual == sc["expected_flags"]
                               and level == sc["expected_overall_confidence_level"]})
    gate_results = []
    for i, name in enumerate(GATES, 1):
        rec = gate_records.get(i)
        gate_results.append({"gate": i, "name": name,
                             "decision": rec.get("decision") if rec else None,
                             "decided_by": (rec.get("decided_by") or {}).get("name") if rec else None,
                             "decided_at": rec.get("decided_at") if rec else None,
                             "approved_for_live_action": rec.get("approved_for_live_action") if rec and i == 5 else None})
    report_path = ROOT / f"reports/generated/{WORKFLOW_SLUG}-{date}-{fset}.md"
    log_path = ROOT / f"logs/{WORKFLOW_SLUG}-{date}-{fset}.json"
    audit_path = ROOT / f"data/verified/{WORKFLOW_SLUG}/runs/{run}/{run}-audit.md"
    pending = [f"{g['gate']} ({g['name']})" for g in gate_results if not g["decision"]]
    if stopped:
        next_decision = "Read the shape findings and fix the sources; detection did not run on this set."
    elif pending:
        next_decision = f"Read the flags and the audit, then decide gate(s) {', '.join(pending)} for this sample run."
    else:
        next_decision = "All six gates are decided for this sample run; nothing further is pending in sample mode."
    if gate_results[4]["decision"] == "deny":
        next_decision += " Live mode is denied (gate 5); reopening it is a separate decision."


    # ── agent log (contract fields) ───────────────────────────────────────────────────────────────────
    agent_log = {"workflow": WORKFLOW_SLUG, "run_id": run, "mode": env["mode"], "steps_completed": completed,
                 "records_seen": records_seen, "rejects": all_rejects, "duplicates": duplicates, "not_checked": not_checked,
                 "flags": [{"flag_id": f["flag_id"], "pattern_id": f["pattern_id"], "severity": f["severity"],
                            "ticker": f["ticker"], "requires_human_review": f["requires_human_review"]} for f in flags],
                 "stop_conditions": [c for _, cs in stopped for c in (cs or [])], "todo_items": todos,
                 "source_files": [s["path"] for s in s2.get("sources", []) if s.get("path")],
                 "gate_decisions": gate_results, "generated_at": env["frozen_clock"],
                 "raw_output_paths": [f"data/raw/{WORKFLOW_SLUG}/runs/{run}/"],
                 "verified_output_paths": [f"data/verified/{WORKFLOW_SLUG}/runs/{run}/"], "report_path": rel(report_path)}
    write(log_path, json.dumps(agent_log, indent=2, sort_keys=True, ensure_ascii=False))

    # ── audit ─────────────────────────────────────────────────────────────────────────────────────────
    A = [f"# Audit: {WORKFLOW_SLUG}, run `{run}`", "",
         "> What this run found, step by step. It reports; it does not approve. Approval is a gate decision by a named human.", "",
         f"- Mode: **{env['mode']}** · fixture set: **{fset}** · frozen clock: `{env['frozen_clock']}`",
         f"- Corpus: synthetic, fictional companies (see `data/raw/{WORKFLOW_SLUG}/sample/FIXTURE_MANIFEST.md`)",
         "- Live calls made: **none** · network access: **none**", "", "## Records in, records out", "",
         "| Step | In | Out | Withheld / findings |", "|---|---|---|---|",
         f"| 2 ingest | {len(s2.get('sources', []))} sources | {records_seen} rows | {sum(1 for s in s2.get('sources', []) if s.get('parsed') is False)} source(s) unparseable, carried as-is |"]
    for src in s3.get("sources", []):
        A.append(f"| 3 shape: {src['source_name']} | {src.get('record_count', '—')} | {src.get('promoted', '—')} | "
                 f"{len(src.get('row_findings', []))} row finding(s), {len(src.get('parse_errors', []))} parse error(s) |")
    if s4:
        A.append(f"| 4 quality | — | {s4.get('verified_records', '—')} | {len(duplicates)} duplicate(s), {len(rejects)} reject(s), "
                 f"{len(stale)} stale row(s) kept |")
    if s5:
        A.append(f"| 5 detection | {len(dets)} companies | {len(flags)} flag(s) | LLM review prepared, not sent |")
    A += ["", "## What was withheld, and why", ""]
    if not (shape or parse or rejects or duplicates):
        A.append("Nothing was withheld.")
    for src, e in parse:
        A.append(f"- **{src}**: unparseable source. {e}")
    for src, rf in shape:
        A.append(f"- **{src}** row " + (f"`{rf['id']}`" if rf.get("id") else "(not an object)") + f" (index {rf['index']}): " +
                 "; ".join(f"{x['problem']}" + (f" on `{x['field']}`" if x.get("field") else "") for x in rf["findings"]))
    for d in duplicates:
        A.append(f"- **{d['source']}** `{d['id']}`: duplicate, {d['action']}")
    for r in rejects:
        A.append(f"- **{r['source']}** `{r['id']}`: {r['reason']}")
    A += ["", "## Kept, but worth a human look", ""]
    A += ([f"- **{r['source']}** `{r['id']}` dated {r['date']}: {r['note']}" for r in stale] or ["Nothing."]) if s4 else \
         ["Not checked: step 4 (quality) did not run, so duplicates and rows older than the lookback were not looked for."]
    if manifest and fset == "defective":
        n3 = sum(1 for d in manifest["defects"] if d["expected_detection"]["step"] == 3)
        n4 = len(manifest["defects"]) - n3
        A += ["", "## Catalogued defects in this corpus", "",
              f"The manifest catalogues {len(manifest['defects'])} defects: {n3} for step 3 (shape) and {n4} for step 4 (quality). "
              + ("This run stopped at step 3, so the step-4 defects were not reached here. " if not s4 else "")
              + "The self-test checks every one mechanically, running step 4 on its own where needed "
              "(logs/contradiction-detection-agent/self-test-results.json)."]
    if comparison:
        A += ["", "## Expected versus actual (clean corpus)", "", "| Company | Expected flags | Actual flags | Same flags and level |",
              "|---|---|---|---|"] + [f"| {c['ticker']} | {c['expected_flags']} | {c['actual_flags']} | {'yes' if c['matches'] else '**NO**'} |"
                                     for c in comparison]
    write(audit_path, "\n".join(A))

    # ── human report ──────────────────────────────────────────────────────────────────────────────────
    R = [f"# Contradiction detection: sample run `{run}`", "",
         "**Reader:** the domain lead who decides whether this run moves forward.  ",
         "**Decision enabled:** approve the run for the next phase, request source or schema fixes, or block live execution.", "",
         "## Run summary", "",
         f"- {len(dets)} fictional companies checked, {len(flags)} disagreement flag(s) raised, every one routed to a human."
         if dets else f"- Detection did not run: the run stopped at {', '.join(s for s, _ in stopped) or 'an earlier step'}.",
         f"- Mode **{env['mode']}**: no database, API or model was contacted.", "",
         "## Purpose", "",
         "Find places where a company's own statements and the outside signals about it disagree (earnings guidance, "
         "risk admissions, analyst Q&A, news sentiment, engineering activity), and hand each disagreement to a human. "
         "The detector surfaces conflict; it does not resolve it, and it never recommends buying or selling.", "",
         "## Source inventory", "", "| Source | Stands for (original node) | Rows | Parsed |", "|---|---|---|---|"]
    R += [f"| {s['source_name']} | {s.get('original_node') or '—'} | {s.get('record_count', '—')} | "
          f"{'yes' if s.get('parsed') else 'NO' if s.get('parsed') is False else '—'} |"
          for s in s2.get("sources", [])] or ["| — | step 2 did not run | — | — |"]
    R += ["", "## Inputs used", "", f"- Run envelope: `data/raw/{WORKFLOW_SLUG}/run-envelope.json` (`run_id` {env['run_id']}, "
          f"lookback {env.get('lookback_days')} days, patterns {env.get('active_patterns')})",
          f"- Fixture set `{fset}` under `data/raw/{WORKFLOW_SLUG}/sample/{fset}/`",
          "- Original workflow: `data/mycroft-main/n8n-workflows/originals/n8n_Workflows/Contradiction_Detection_Agent/Contradiction_detection_agent.json`",
          "", "## Phase-gate results", "", "| Gate | Decision | By | When |", "|---|---|---|---|"]
    R += [f"| {g['gate']}. {g['name']} | {g['decision'] or 'not yet decided'} | {g['decided_by'] or '—'} | {g['decided_at'] or '—'} |"
          for g in gate_results]
    R += ["", "## Steps completed", ""] + [f"- {i + 1}. {s}: {'completed' if s in completed else 'STOPPED' if any(s == x for x, _ in stopped) else 'not run'}"
                                           for i, s in enumerate(STEPS[:5])]
    R += ["", "## Records seen", "", f"{records_seen} rows across {len(s2.get('sources', []))} sources (details in the audit).",
          "", "## Rejects", "", f"{len(all_rejects)} (shape findings {len(shape)}, unparseable sources {len(parse)}, "
          + (f"quality rejects {len(rejects)})." if s4 else "quality rejects not checked: step 4 did not run).")
          + " Each is listed with its reason in the audit and the agent log.", "",
          "## Duplicates", "", f"{len(duplicates)} (the later copy withheld in each case)." if s4 else
          "Not checked: step 4 (quality) did not run, so duplicates were not looked for.", "", "## Flags", ""]
    if flags:
        R += ["| Company | Pattern | Severity | What disagrees | Reading note |", "|---|---|---|---|---|"]
        R += [f"| {f['ticker']} | {f['pattern_id']}. {f['pattern_name']} | {f['severity']} | {f['conflict_description']} | "
              f"{reading_note(f, flags)} |" for f in flags]
    else:
        R.append("None raised.")
    R += ["", "## Typed TODOs", ""] + ([f"- {t}" for t in todos] or ["None open."])
    R += ["", "## Human approvals", "", "Recorded gate decisions are listed above. Nothing in this run was approved by a machine.",
          "", "## Verified findings", "",
          "- Each flag is a **detected disagreement between two named sources**, computed by the ported detector, "
          "whose output matches the original workflow's JavaScript on every sample company (parity check)." if dets else
          "- None: detection did not run on this set.",
          ("- Not checked: step 4 did not run, so the age of the evidence was not examined." if not s4 else
           f"- {len(stale)} row(s) older than the declared lookback were used, as the original queries select without a date filter." if stale else
           "- No evidence older than the declared lookback was used."), "", "## Inferred findings", "",
          "None. The optional LLM review (the original's analyst memo, plausibility and relevance scores) was prepared "
          "as a handoff and **not sent**; it needs a gate-5 approval naming a human.", "", "## Decision recommendation", "",
          next_decision, ""]
    write(report_path, "\n".join(R))

    result = {"workflow": WORKFLOW_NAME, "node": NODE_NAME, "node_type": NODE_TYPE, "classification": CLASSIFICATION,
              "run": run, "summary": f"{len(dets)} companies, {len(flags)} flags, {len(completed)}/5 steps completed",
              "sources_checked": len(s2.get("sources", [])), "gate_results": gate_results,
              "findings": {"flags": len(flags), "shape_findings": len(shape), "parse_errors": len(parse),
                           "rejects": len(rejects), "duplicates": len(duplicates), "stale_kept": len(stale),
                           "expected_vs_actual_mismatches": sum(1 for c in comparison if not c["matches"])},
              "typed_todos": todos, "next_decision": next_decision,
              "outputs": {"report": rel(report_path), "agent_log": rel(log_path), "audit": rel(audit_path)},
              "status": "ok", "stop_conditions": [], "live_call_performed": False, "network_access": "none",
              "human_gate": {"gate": 6, "capacity": "[TO]", "cleared_by": None,
                             "note": "Gate 6: the report and log exist with the contract's fields and sections."}}
    text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)
    if a.output:
        write(Path(a.output), text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
