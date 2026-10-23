"""Week 2: the answer key for every report the evaluation uses (DESIGN.md §11, week 2).

Week 1 loaded 10 companies (`load_answer_key.py`). This builds all of them — the 25 AI companies
and the 75 in the generalisation set — for every 10-Q/10-K in the notes data (reports for quarters
from mid-2024 to mid-2026), at all three levels, and checks it is fit to grade against:

* one JSON record per report in `$AI_DEBT_DATA/answer_key/<cik>/<accession>.json` (instruments,
  totals, the report's grading level and coverage);
* every episode in `manifests/dev.csv` and `test.csv` must find its start and target record;
* anomalies are counted, not hidden: reports with no total-debt tag, itemised coverage above 120%
  (double counting), and L1 reports where a bond has no principal.

Writes docs/answer_key.md (for people) and `$AI_DEBT_DATA/answer_key/index.json` (for code).

Usage:  python scripts/build_answer_key.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ai_debt_tracker import config
from ai_debt_tracker.eval.answer_key import AnswerKey, grading_level
from ai_debt_tracker.eval.grader import truth_bonds, truth_totals, truth_units
from review_universe import DEV, TEST, extracted_periods, gate_status, nearest_quarter_end

ROOT = Path(__file__).resolve().parents[1]
OUT = config.data_dir() / "answer_key"


def manifest(name):
    with open(ROOT / "manifests" / name, encoding="utf-8") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def main() -> int:
    universe = json.loads((ROOT / "universe_v1.json").read_text(encoding="utf-8"))
    cos = [{"cik": c["cik"], "name": c["name"], "universe": "ai25", "group": c["group"]} for c in universe["companies"]]
    cos += [{"cik": int(g["cik"]), "name": g["name"], "universe": "gen", "group": g["division"]}
            for g in manifest("generalisation.csv")]
    ak = AnswerKey(extracted_periods(), {c["cik"] for c in cos})
    index, per_co, anomalies = {}, [], Counter()
    examples = defaultdict(list)
    for co in cos:
        reports = ak.reports(co["cik"])
        levels, bonds, last = Counter(), 0, None
        for r in reports:
            rec = ak.filing_record(r["adsh"])
            g = grading_level(rec)
            rec["grading"] = g
            rec["truth"] = {"bonds": len(truth_bonds(rec)), "units": len(truth_units(rec)), "totals": truth_totals(rec)}
            d = OUT / str(co["cik"])
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{r['adsh']}.json").write_text(json.dumps(rec, default=str))
            q = nearest_quarter_end(r["period"])
            index[r["adsh"]] = {"cik": co["cik"], "form": r["form"], "period": r["period"], "quarter_end": q,
                                "level": g["level"], "bonds": rec["truth"]["bonds"], "has_total": "total_debt" in rec["truth"]["totals"]}
            levels[g["level"]] += 1
            # anomalies worth a look before anything is graded against this
            if "total_debt" not in rec["truth"]["totals"]:
                anomalies["no total-debt tag"] += 1
                examples["no total-debt tag"].append(f"{co['name']} {r['form']} {r['period']}")
            if g["coverage_itemised"] > 1.2 and not g["total_basis"].startswith("sum of tagged"):
                anomalies["itemised coverage > 120%"] += 1
                examples["itemised coverage > 120%"].append(f"{co['name']} {r['form']} {r['period']} ({g['coverage_itemised']:.0%})")
            if g["level"] == "L1" and any(b["principal"] is None for b in truth_bonds(rec)):
                anomalies["L1 report with a bond lacking principal"] += 1
                examples["L1 report with a bond lacking principal"].append(f"{co['name']} {r['form']} {r['period']}")
            last = (r, rec)
            bonds += rec["truth"]["bonds"]
        per_co.append({**co, "reports": len(reports), "levels": dict(levels),
                       "latest": f"{last[0]['form']} {last[0]['period']}" if last else "—",
                       "latest_bonds": last[1]["truth"]["bonds"] if last else 0,
                       "latest_total_bn": (last[1]["truth"]["totals"].get("total_debt") or 0) / 1e9 if last else 0})
        print(f"{co['universe']:4s} {co['name'][:30]:30s} {len(reports):2d} reports {dict(levels)}", flush=True)
    (OUT / "index.json").write_text(json.dumps(index, indent=0))

    # every episode must find both of its records
    missing = []
    for split in ("dev", "test"):
        for e in manifest(f"{split}.csv"):
            for k in ("start_adsh", "target_adsh"):
                if e[k] not in index:
                    missing.append(f"{split} {e['episode_id']} {k}")
    # the answer-key rules improve after a freeze; the frozen levels do not move with them, so say
    # where today's rules would disagree (P6: a mismatch is logged, not silently resolved)
    drift = []
    for split in ("dev", "test"):
        for e in manifest(f"{split}.csv"):
            now = index.get(e["target_adsh"], {}).get("level")
            if now and now != e["target_level"]:
                drift.append(f"{split} {e['company']} {e['target_form']} {e['target_period']}: frozen {e['target_level']}, now {now}")
    write_doc(per_co, index, anomalies, examples, missing, drift)
    print(f"\n{len(index)} report records; episodes missing a record: {len(missing)}; anomalies {dict(anomalies)}")
    return 1 if missing else 0


def write_doc(per_co, index, anomalies, examples, missing, drift):
    lv = Counter(v["level"] for v in index.values())
    in_window = [v for v in index.values() if DEV[0] <= v["quarter_end"] <= TEST[1]]
    L = ["# Answer key — all 100 companies\n",
         "> Generated by `scripts/build_answer_key.py` from the SEC Financial Statement and Notes data. One record per "
         "report in `$AI_DEBT_DATA/answer_key/<cik>/<accession>.json` (local, not in git), indexed in `index.json`. "
         f"Grader side only (P11). Universe and generalisation set: {gate_status()}.\n",
         "## Coverage\n",
         f"- **{len(index)}** reports from **{len(per_co)}** companies "
         f"({sum(c['universe'] == 'ai25' for c in per_co)} AI, {sum(c['universe'] == 'gen' for c in per_co)} generalisation); "
         f"{len(in_window)} of them for quarters inside the dev and test windows.",
         f"- Finest level each report supports: **L1 {lv['L1']}**, **L2 {lv['L2']}**, **L3 {lv['L3']}**.",
         f"- Bonds in the key (outstanding, with a maturity year): **{sum(v['bonds'] for v in index.values()):,}**.",
         f"- Episodes in `manifests/dev.csv` and `test.csv` without their start or target record: **{len(missing)}**.\n",
         "## Anomalies (counted, not hidden)\n",
         "| Check | Reports | Examples |", "|---|---|---|"]
    for k in ("no total-debt tag", "itemised coverage > 120%", "L1 report with a bond lacking principal"):
        ex = "; ".join(examples[k][:4]) + (" …" if len(examples[k]) > 4 else "")
        L.append(f"| {k} | {anomalies.get(k, 0)} | {ex or '—'} |")
    L.append("\n*No total-debt tag*: the report's L3 total cannot be graded; its L1/L2 grading is unaffected. "
             "*Coverage > 120%*: tagged instruments add up to more than reported debt, usually face vs net carrying "
             "amounts or a subtotal tagged beside its parts. *Bond lacking principal*: matched on coupon and year, "
             "unscored on amount.\n")
    L.append("## Frozen levels vs today's rules\n")
    L.append(f"Episode target levels were frozen at the Week 1 gate. Re-graded with today's answer-key rules, "
             f"**{len(drift)}** of the {sum(1 for s in ('dev', 'test') for _ in manifest(s + '.csv'))} episode targets "
             "would get a different level. Episodes are still graded at their frozen level; a change needs a new gate.\n")
    L += [f"- {d}" for d in drift[:20]] + ([f"- … and {len(drift) - 20} more"] if len(drift) > 20 else []) + [""]
    L.append("## AI companies\n")
    L.append("| Company | Group | Reports | Levels | Latest report | Bonds in latest | Total debt $bn |")
    L.append("|---|---|---|---|---|---|---|")
    for c in per_co:
        if c["universe"] == "ai25":
            L.append(f"| {c['name']} | {c['group']} | {c['reports']} | "
                     + ", ".join(f"{k} {v}" for k, v in sorted(c["levels"].items()))
                     + f" | {c['latest']} | {c['latest_bonds']} | {c['latest_total_bn']:,.1f} |")
    gen = [c for c in per_co if c["universe"] == "gen"]
    L.append(f"\n## Generalisation set\n\n{len(gen)} companies, {sum(c['reports'] for c in gen)} reports, "
             f"{sum(c['latest_bonds'] for c in gen):,} bonds in their latest reports. Per-company detail is in "
             "`index.json`.\n")
    (ROOT / "docs" / "answer_key.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
