"""Purpose: Run every check this recipe's evidence rests on, in throwaway copies of the tree, and record each result to a file.
Input: this recipe's scripts, sample corpus, recipe text and the original workflow JSON (all read from the repo, never modified).
Output: logs/contradiction-detection-agent/self-test-results.json (machine view) and .md (human view); a summary on stdout. Exit 0 only if every check behaved as expected.
Side effects: writes those two files. Every break test runs in a temporary copy, which is deleted afterwards. No network.
Idempotent: Yes; the corpus and clock are frozen, and temporary copies are fresh each time.
Recipe: recipes/contradiction-detection-agent.md

Why it exists. "Break tests were run" is a claim; a script that runs them and writes down what it saw
is evidence (P3). Every check states what it ran, what it saw and what was expected, the same three
columns an attestation uses, so a human can attest from this record instead of from memory.

Sections:
  A. Defect catalogue: each of the manifest's defects is detected by the step it names, at its row.
  B. Parity: the Python detector matches the original JavaScript on every sample company, and the
     parity check catches three deliberately broken ports (it can fail).
  C. Break tests: empty tree, live mode, changed fixture, repaired broken file, renamed node, step 5
     before step 4, and no half-built bundles from a stopped step 4.
  D. Gates: every gate test of this recipe fails on an empty tree.
  E. Determinism: two clean runs produce byte-identical outputs.
  F. The recipe's frontmatter todos_open equals its open typed TODOs.
  G. Report and agent log agree: same reject count, nothing unchecked reported as zero, and the
     recommendation names exactly the gates that have no decision record.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
WORKFLOW_SLUG = "contradiction-detection-agent"
ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = "data/mycroft-main/n8n-workflows/originals/n8n_Workflows/Contradiction_Detection_Agent/Contradiction_detection_agent.json"
SAMPLE = f"data/raw/{WORKFLOW_SLUG}/sample"
ENVELOPE = f"data/raw/{WORKFLOW_SLUG}/run-envelope.json"
RESULTS = []


def record(section: str, ran: str, saw: str, expected: str, ok: bool) -> None:
    RESULTS.append({"section": section, "ran": ran, "saw": saw, "expected": expected, "as_expected": bool(ok)})
    print(f"  [{'ok' if ok else 'UNEXPECTED'}] {section}: {ran}")


def tree(with_outputs: bool = False) -> Path:
    """A throwaway copy holding only this recipe's own files (+ the original workflow JSON it reads)."""
    t = Path(tempfile.mkdtemp(prefix="cda-selftest-"))
    keep = [f"recipes/{WORKFLOW_SLUG}.md", ORIGINAL, SAMPLE, ENVELOPE]
    keep += [str(p.relative_to(ROOT)) for p in (ROOT / "scripts").rglob(f"{WORKFLOW_SLUG}-*.py")]
    for rel in keep:
        src, dst = ROOT / rel, t / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return t


def run(t: Path, layer_step: str, *args: str):
    layer, step = layer_step.split("/")
    r = subprocess.run([sys.executable, str(t / f"scripts/{layer}/{WORKFLOW_SLUG}-{step}.py"), *args],
                       capture_output=True, text=True, cwd=t)
    try:
        out = json.loads(r.stdout)
    except ValueError:
        out = {}
    return r.returncode, out


def section_a(t: Path) -> None:
    man = json.loads((t / SAMPLE / "fixture-manifest.json").read_text(encoding="utf-8"))
    run(t, "ingest/ingest-inputs", "--fixture-set", "defective")
    c3, s3 = run(t, "gigo/validate-data-shape", "--fixture-set", "defective")
    c4, s4 = run(t, "gigo/transform-quality-check", "--fixture-set", "defective")
    record("A", "step 3 on the defective set", f"exit {c3}, status {s3.get('status')}", "exit 1: shape defects halt the run",
           c3 == 1)
    f3 = {(s["source_name"], rf.get("id"), x["problem"], x["field"]) for s in s3.get("sources", [])
          for rf in s["row_findings"] for x in rf["findings"]}
    parse = {s["source_name"] for s in s3.get("sources", []) if s["parse_errors"]}
    rej = {(r["source"], r["id"]) for r in s4.get("rejects", [])}
    dup = {(d["source"], d["id"]) for d in s4.get("duplicates", [])}
    stale = {(r["source"], r["id"]) for r in s4.get("stale_rows", [])}
    want = {"missing_required": "missing_required", "row_not_object": "row_not_object", "type_error": "type_error",
            "enum": "not_in_allowed_set", "bounds": "out_of_bounds"}
    for d in man["defects"]:
        src, rid, fld, cls = d["source"], d["locator"].get("row_id"), d["field"], d["class"]
        if cls == "unparseable_file":
            hit = src in parse
        elif d["expected_detection"]["step"] == 3:
            hit = any(s == src and p == want[cls] and (cls == "row_not_object" or (i == rid and f == fld)) for s, i, p, f in f3)
        elif cls == "duplicate":
            hit = (src, rid) in dup
        elif cls == "stale":
            hit = (src, rid) in stale
        else:
            hit = (src, rid) in rej
        record("A", f"{d['id']} {cls} in {src} ({rid or d['locator'].get('file')})",
               "detected" if hit else "missed", f"detected by step {d['expected_detection']['step']}", hit)
    catalogued3 = sum(1 for d in man["defects"] if d["expected_detection"]["step"] == 3 and d["class"] != "unparseable_file")
    record("A", "step-3 findings outside the catalogue", f"{len(f3) - catalogued3}", "0 (no false findings)",
           len(f3) == catalogued3)


def section_b(t: Path) -> None:
    c, out = run(t, "tools/parity-check")
    record("B", "parity check, real port, clean set", f"exit {c}, {out.get('agree')}/{out.get('companies')} companies agree",
           f"exit 0, all agree", c == 0 and out.get("agree") == out.get("companies"))
    mutations = {
        "threshold 0.6 -> 0.61": ('num(g.get("direction_confidence")) >= 0.6]', 'num(g.get("direction_confidence")) >= 0.61]'),
        "Python rounding instead of JS toFixed": ("return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))", "return f'{x:.2f}'"),
        "Python number-to-text instead of JS": ("        if v.is_integer() and abs(v) < 1e21:\n            return str(int(v))\n", ""),
    }
    port = t / f"scripts/tools/{WORKFLOW_SLUG}-run-approved-tools.py"
    good = port.read_text(encoding="utf-8")
    for name, (old, new) in mutations.items():
        port.write_text(good.replace(old, new, 1), encoding="utf-8")
        c, out = run(t, "tools/parity-check")
        bad = [r["ticker"] for r in out.get("results", []) if r["status"] != "agree"]
        record("B", f"parity check against a deliberately broken port ({name})", f"exit {c}, disagreeing {bad}",
               "exit 1: the break is caught", c == 1 and bool(bad))
    port.write_text(good, encoding="utf-8")


def section_c() -> None:
    t = Path(tempfile.mkdtemp(prefix="cda-empty-"))
    for p in (ROOT / "scripts").rglob(f"{WORKFLOW_SLUG}-*.py"):
        dst = t / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
    c, out = run(t, "tools/verify-provenance")
    record("C", "step 1 on an empty tree (scripts only)", f"exit {c}, {len(out.get('stop_conditions', []))} stop condition(s)",
           "exit 1, naming every missing source", c == 1 and len(out.get("stop_conditions", [])) >= 4)
    shutil.rmtree(t)

    t = tree()
    env = json.loads((t / ENVELOPE).read_text(encoding="utf-8"))
    (t / ENVELOPE).write_text(json.dumps({**env, "mode": "live"}), encoding="utf-8")
    c2, o2 = run(t, "ingest/ingest-inputs")
    c5, o5 = run(t, "tools/run-approved-tools")
    record("C", "live mode in the envelope, steps 2 and 5", f"step 2 exit {c2}, step 5 exit {c5}; "
           f"names credentials: {'ALPHA_VANTAGE_API_KEY' in json.dumps(o2)}",
           "both exit 1 before any connection, naming what live mode would need",
           c2 == 1 and c5 == 1 and "ALPHA_VANTAGE_API_KEY" in json.dumps(o2) and not o2.get("live_call_performed"))
    shutil.rmtree(t)

    t = tree()
    f = t / SAMPLE / "clean/news-signals.json"
    f.write_text(f.read_text(encoding="utf-8").replace('"positive"', '"negative"', 1), encoding="utf-8")
    c, out = run(t, "tools/verify-provenance")
    record("C", "one fixture value changed after the manifest froze it", f"exit {c}: {out.get('stop_conditions')}",
           "exit 1: fixture changed since the manifest froze it", c == 1 and "changed since" in json.dumps(out))
    shutil.rmtree(t)

    t = tree()
    broken = t / SAMPLE / "defective/qa-pressure-map.json.broken"
    clean_qa = (t / SAMPLE / "clean/qa-pressure-map.json").read_text(encoding="utf-8")
    broken.write_text(clean_qa, encoding="utf-8")  # someone "repairs" the deliberately broken fixture
    c, out = run(t, "tools/verify-provenance")
    record("C", "the deliberately unparseable fixture 'repaired'", f"exit {c}", "exit 1: the defect corpus can't silently lose a defect",
           c == 1)
    shutil.rmtree(t)

    t = tree()
    rp = t / f"recipes/{WORKFLOW_SLUG}.md"
    rp.write_text(rp.read_text(encoding="utf-8").replace("| Fan Out Flags |", "| Fan Out Every Flag |", 1), encoding="utf-8")
    c, out = run(t, "tools/verify-provenance")
    record("C", "a node renamed in the recipe's node table", f"exit {c}: {out.get('stop_conditions')}",
           "exit 1: the recipe no longer describes its source", c == 1 and "node table mismatch" in json.dumps(out))
    shutil.rmtree(t)

    t = tree()
    c, out = run(t, "tools/run-approved-tools")
    record("C", "step 5 before steps 2-4 have run", f"exit {c}: {out.get('stop_conditions')}",
           "exit 1: no verified bundles", c == 1)
    run(t, "ingest/ingest-inputs", "--fixture-set", "defective")
    run(t, "gigo/validate-data-shape", "--fixture-set", "defective")
    c4, _ = run(t, "gigo/transform-quality-check", "--fixture-set", "defective")
    left = list((t / f"data/verified/{WORKFLOW_SLUG}/runs/sample-001-defective/quality-checked").glob("*.json"))
    record("C", "step 4 stopping on the defective set", f"exit {c4}, {len(left)} bundle(s) written",
           "exit 1 and no half-built bundles for step 5 to pick up", c4 == 1 and not left)
    shutil.rmtree(t)


def section_d() -> None:
    # This recipe's gate tests: each must FAIL on an empty tree (scripts only, nothing run).
    t = Path(tempfile.mkdtemp(prefix="cda-gates-"))
    for p in (ROOT / "scripts").rglob(f"{WORKFLOW_SLUG}-*.py"):
        dst = t / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
    for g in range(1, 7):
        c, out = run(t, "tools/gate-check", "--gate", str(g))
        record("D", f"gate {g} test on an empty tree", f"exit {c}: {out.get('reason', '')[:120]}", "exit 1: fails", c == 1)
    shutil.rmtree(t)


def section_g() -> None:
    """The recipe's lifecycle claim matches the recipe: todos_open equals the open markers outside code spans."""
    text = (ROOT / f"recipes/{WORKFLOW_SLUG}.md").read_text(encoding="utf-8")
    fm = re.search(r"^---\n(.*?)\n---\n", text, re.S)
    declared = re.search(r"^todos_open:\s*(\d+)", fm.group(1), re.M) if fm else None
    open_items = re.findall(r"\[TODO: [A-Z ]+\]", re.sub(r"`[^`\n]*`", "", text))
    record("F", "frontmatter todos_open against the open typed TODOs in the recipe",
           f"declared {declared.group(1) if declared else None}, found {len(open_items)}: {open_items}",
           "equal", bool(declared) and int(declared.group(1)) == len(open_items))


def section_h() -> None:
    t = tree()
    shutil.copytree(ROOT / "logs/gate-decisions", t / "logs/gate-decisions", dirs_exist_ok=True)
    undecided = [g for g in range(1, 7) if not (t / f"logs/gate-decisions/{WORKFLOW_SLUG}-gate-{g}.json").exists()]
    date = json.loads((t / ENVELOPE).read_text(encoding="utf-8"))["frozen_clock"][:10]
    for fset in ("clean", "defective"):
        subprocess.run([sys.executable, str(t / f"scripts/tools/{WORKFLOW_SLUG}-run-sample.py"), "--fixture-set", fset],
                       capture_output=True, text=True, cwd=t)
        rep_text = (t / f"reports/generated/{WORKFLOW_SLUG}-{date}-{fset}.md").read_text(encoding="utf-8")
        log = json.loads((t / f"logs/{WORKFLOW_SLUG}-{date}-{fset}.json").read_text(encoding="utf-8"))
        m = re.search(r"## Rejects\n\n(\d+) ", rep_text)
        n_report = int(m.group(1)) if m else None
        record("G", f"{fset} run: rejects in the report against rejects in the agent log",
               f"report {n_report}, log {len(log['rejects'])}", "equal", n_report == len(log["rejects"]))
        rec = re.search(r"## Decision recommendation\n\n(.*)", rep_text).group(1)
        if fset == "defective":
            dup = re.search(r"## Duplicates\n\n(.*)", rep_text).group(1)
            record("G", "defective run (stopped at step 3): what the report and log say about step-4 checks",
                   f"duplicates: {dup[:40]!r}; log not_checked: {log.get('not_checked')}",
                   "'Not checked' in the report and listed in the log, not reported as 0",
                   dup.startswith("Not checked") and bool(log.get("not_checked")))
        else:
            named = sorted(int(x) for x in re.findall(r"(\d) \(", rec))
            record("G", "clean run: gates the recommendation asks a human to decide", f"{named} ({rec[:60]}...)",
                   f"exactly the gates with no decision record: {undecided}", named == undecided)
    shutil.rmtree(t)


def section_f() -> None:
    hashes = []
    for _ in range(2):
        t = tree()
        subprocess.run([sys.executable, str(t / f"scripts/tools/{WORKFLOW_SLUG}-run-sample.py"), "--fixture-set", "clean"],
                       capture_output=True, text=True, cwd=t)
        outs = sorted(p for d in ("data/verified", "logs", "reports") if (t / d).exists() for p in (t / d).rglob("*") if p.is_file())
        h = hashlib.sha256()
        for p in outs:
            h.update(str(p.relative_to(t)).encode())
            h.update(p.read_bytes())
        hashes.append((len(outs), h.hexdigest()[:16]))
        shutil.rmtree(t)
    record("E", "the full clean run, twice, in two fresh trees", f"{hashes[0][0]} files, digests {hashes[0][1]} / {hashes[1][1]}",
           "byte-identical outputs", hashes[0] == hashes[1])


def main() -> int:
    print("self-test:")
    t = tree()
    section_a(t)
    section_b(t)
    shutil.rmtree(t)
    section_c()
    section_d()
    section_f()
    section_g()
    section_h()
    bad = [r for r in RESULTS if not r["as_expected"]]
    summary = {"workflow": WORKFLOW_SLUG, "checks": len(RESULTS), "as_expected": len(RESULTS) - len(bad),
               "unexpected": len(bad), "results": RESULTS, "network_access": "none", "live_call_performed": False}
    out = ROOT / f"logs/{WORKFLOW_SLUG}/self-test-results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    md = ["# Self-test results: contradiction-detection-agent", "",
          f"{len(RESULTS)} checks, {len(RESULTS) - len(bad)} behaved as expected, {len(bad)} did not. "
          "Generated by `scripts/tools/contradiction-detection-agent-self-test.py`; every break test ran in a throwaway copy.", "",
          "| Section | Ran | Saw | Expected | As expected |", "|---|---|---|---|---|"]
    md += [f"| {r['section']} | {r['ran']} | {str(r['saw']).replace('|', '/')} | {r['expected']} | {'yes' if r['as_expected'] else '**NO**'} |"
           for r in RESULTS]
    with open(out.with_suffix(".md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md) + "\n")
    print(f"{len(RESULTS)} checks · {len(RESULTS) - len(bad)} as expected · {len(bad)} unexpected → {out.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
