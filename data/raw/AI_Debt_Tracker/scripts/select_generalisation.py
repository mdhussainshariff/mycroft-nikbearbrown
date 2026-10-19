"""Week 1: pick the ~75-company generalisation set (DESIGN.md §3.2, §3.5) by a fixed rule.

The test split adds non-AI companies so the evaluation does not rest on 25 names. Which companies
is a scope decision (P1: humans decide scope), so this script does not choose — it applies a rule
written down in advance and proposes the result for sign-off:

1. Candidates: US filers of 10-Q/10-K in the notes data, not in the AI universe (nor one of its
   issuing subsidiaries), and outside
     - finance, insurance and real estate (SIC 6000–6799: bank notes, CLOs and securitisations
       are a different instrument world), and
     - AI-adjacent industries (SIC 3570–3579 computers, 3670–3679 semiconductors and components,
       7370–7379 software and data processing), so the set is genuinely "non-AI".
2. Screen: every report whose calendar quarter end falls in the **test** window (Sep 2025 –
   Jun 2026) must exist, and at least 3 of those 4 must grade at L1 under the answer-key coverage
   rule — the generalisation set is graded per bond, like the AI L1 companies.
3. Spread across industries: at most 3 companies per 2-digit SIC major group; within that, larger
   total debt first (big issuers are the frequent ones). Take the first 75 in that order,
   round-robin across major groups so no industry dominates. Ties break on CIK.

Writes manifests/generalisation.csv (status: proposed) and prints a summary.

Usage:  python scripts/select_generalisation.py [N=75]
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ai_debt_tracker.eval.answer_key import AnswerKey, grading_level
from ai_debt_tracker.eval.fsn import month_dir, read_tsv
from review_universe import TEST, extracted_periods, gate_status, nearest_quarter_end

ROOT = Path(__file__).resolve().parents[1]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 75
PER_GROUP = 3
EXCLUDED_SIC = [(6000, 6799, "finance, insurance, real estate"), (3570, 3579, "computers"),
                (3670, 3679, "semiconductors / components"), (7370, 7379, "software / data processing")]
DIVISIONS = [(100, 999, "Agriculture"), (1000, 1499, "Mining"), (1500, 1799, "Construction"),
             (2000, 3999, "Manufacturing"), (4000, 4999, "Transportation, communications, utilities"),
             (5000, 5199, "Wholesale"), (5200, 5999, "Retail"), (6000, 6799, "Finance"), (7000, 8999, "Services"),
             (9100, 9999, "Public administration")]


def division(sic: int) -> str:
    return next((d for lo, hi, d in DIVISIONS if lo <= sic <= hi), "Other")


def main() -> int:
    universe = json.loads((ROOT / "universe_v1.json").read_text(encoding="utf-8"))
    ai = {c["cik"] for c in universe["companies"]} | {s["cik"] for c in universe["companies"] for s in c["issuing_subsidiaries"]}
    periods = extracted_periods()
    test_periods = [p for p in periods if p >= "2025q3"]  # reports for Sep 2025 – Jun 2026 quarters are filed from Oct 2025

    # 1. candidates by industry and country, with enough per-instrument debt facts to be worth loading
    info, facts = {}, Counter()
    for p in test_periods:
        subs = {}
        for r in read_tsv(month_dir(p) / "sub.tsv"):
            sic = int(r["sic"] or 0)
            if r["countryba"] != "US" or int(r["cik"]) in ai or any(lo <= sic <= hi for lo, hi, _ in EXCLUDED_SIC) or not sic:
                continue
            subs[r["adsh"]] = int(r["cik"])
            info[int(r["cik"])] = {"name": r["name"], "sic": sic}
        dims = {r["dimhash"] for r in read_tsv(month_dir(p) / "dim.tsv")}
        for r in read_tsv(month_dir(p) / "num.tsv.gz"):
            if r["adsh"] in subs and r["dimh"] in dims and r["tag"] in ("DebtInstrumentFaceAmount", "DebtInstrumentInterestRateStatedPercentage",
                                                                         "DebtInstrumentCarryingAmount", "LongTermDebt"):
                facts[subs[r["adsh"]]] += 1
    pool = [cik for cik, n in facts.most_common() if n >= 40]
    print(f"candidates: {len(info)} US non-financial non-AI filers; {len(pool)} with >= 40 per-instrument debt facts", flush=True)

    # 2. the L1 screen over the test window
    ak = AnswerKey(periods, set(pool))
    passed = []
    for cik in pool:
        reports = [r for r in ak.reports(cik) if TEST[0] <= nearest_quarter_end(r["period"]) <= TEST[1]]
        quarters = {nearest_quarter_end(r["period"]) for r in reports}
        if len(quarters) < 4:
            continue
        grades = [grading_level(ak.filing_record(r["adsh"])) for r in reports]
        n_l1 = sum(g["level"] == "L1" for g in grades)
        if n_l1 < 3:
            continue
        last = grades[-1]
        passed.append({"cik": cik, "name": info[cik]["name"], "sic": info[cik]["sic"], "sic_group": info[cik]["sic"] // 100,
                       "division": division(info[cik]["sic"]), "test_reports": len(reports), "test_reports_l1": n_l1,
                       "total_debt_usd": last["total_debt"], "total_basis": last["total_basis"],
                       "bonds_keyed_latest": last["counts"].get("bond_keyed", 0)})
    print(f"pass the L1 screen (>= 3 of 4 test reports at L1): {len(passed)}", flush=True)

    # 3. spread across industries
    by_group = defaultdict(list)
    for c in sorted(passed, key=lambda c: (-(c["total_debt_usd"] or 0), c["cik"])):
        if len(by_group[c["sic_group"]]) < PER_GROUP:
            by_group[c["sic_group"]].append(c)
    chosen, rnd = [], 0
    groups = sorted(by_group, key=lambda g: (-(by_group[g][0]["total_debt_usd"] or 0), g))
    while len(chosen) < N and any(len(by_group[g]) > rnd for g in groups):
        for g in groups:
            if rnd < len(by_group[g]) and len(chosen) < N:
                chosen.append(by_group[g][rnd])
        rnd += 1
    for i, c in enumerate(chosen, 1):
        c["rank"] = i

    out = ROOT / "manifests" / "generalisation.csv"
    cols = ["rank", "cik", "name", "sic", "division", "test_reports", "test_reports_l1", "bonds_keyed_latest",
            "total_debt_usd", "total_basis"]
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(f"# status: {gate_status()}; generalisation set for the test split; selection rule in "
                "scripts/select_generalisation.py\n")
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(chosen)
    print(f"chosen: {len(chosen)} across {len({c['sic_group'] for c in chosen})} SIC major groups -> {out.relative_to(ROOT)}")
    print("by division:", dict(Counter(c["division"] for c in chosen)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
