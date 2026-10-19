"""Week 1: fix the dev and test episodes (DESIGN.md §3.5) and write them to manifests/.

An episode is one company and one quarter: start from the report for quarter t, read every filing
in the window, and rebuild the ledger as of the report for quarter t+1, which is withheld.

    start         the previous 10-Q/10-K (public; the opening ledger)
    target        the next 10-Q/10-K (the answer key; withheld from the agent)
    cutoff        the target's EDGAR acceptanceDateTime, exactly as EDGAR's submissions index
                  writes it — the value `edgar_pit` is started with (EDGAR_PIT_AS_OF), so the
                  episode and the server compare times in the same clock
    window_open   30 days before the start period ends (P21: bonds priced before quarter-end)

Splits are by the calendar quarter end nearest the target's period (fiscal quarters differ —
Nvidia's ends in late October), so test is always the future relative to dev:

    dev   Sep 2024 – Jun 2025   AI universe
    test  Sep 2025 – Jun 2026   AI universe + generalisation set

Each episode carries the target report's grading level (answer-key coverage rule) and the P19
check: if the target has fewer than half the outstanding members of the start (from >= 4), the
episode is graded at L3 and flagged. Episodes that cannot be built are counted with a reason,
never dropped silently (§9.5).

Usage:  python scripts/build_splits.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from ai_debt_tracker.edgar import load_filings
from ai_debt_tracker.eval.answer_key import AnswerKey, grading_level
from ai_debt_tracker.sec import SecClient
from review_universe import DEV, TEST, extracted_periods, gate_status, nearest_quarter_end

ROOT = Path(__file__).resolve().parents[1]
COLS = ["episode_id", "split", "universe", "company", "cik", "group", "quarter_end",
        "start_adsh", "start_form", "start_period", "target_adsh", "target_form", "target_period",
        "window_open", "cutoff", "target_level", "graded_level", "p19_downgrade",
        "start_members", "target_members", "target_coverage_itemised", "company_level"]


def members(g: dict) -> int:
    return sum(v for k, v in g["counts"].items() if k != "bond_keyed")


def main() -> int:
    universe = json.loads((ROOT / "universe_v1.json").read_text(encoding="utf-8"))
    with open(ROOT / "manifests" / "generalisation.csv", encoding="utf-8") as f:
        gen = list(csv.DictReader(line for line in f if not line.startswith("#")))
    companies = [{"cik": c["cik"], "name": c["name"], "group": c["group"], "universe": "ai25", "level": c["grading_level"]}
                 for c in universe["companies"]]
    companies += [{"cik": int(g["cik"]), "name": g["name"], "group": g["division"], "universe": "gen", "level": "L1"} for g in gen]
    ak = AnswerKey(extracted_periods(), {c["cik"] for c in companies})
    client = SecClient()
    rows, dropped = {"dev": [], "test": []}, Counter()
    for co in companies:
        reports = ak.reports(co["cik"])
        edgar = load_filings(client, co["cik"])
        grades = {r["adsh"]: grading_level(ak.filing_record(r["adsh"])) for r in reports}
        for start, target in zip(reports, reports[1:]):
            q = nearest_quarter_end(target["period"])
            split = "dev" if DEV[0] <= q <= DEV[1] else "test" if TEST[0] <= q <= TEST[1] else None
            if split is None:
                continue
            if split == "dev" and co["universe"] == "gen":
                continue  # the generalisation set is test-only
            if q == nearest_quarter_end(start["period"]):
                dropped["start and target map to the same quarter"] += 1
                continue
            ref = edgar.get(target["adsh"])
            if ref is None:
                dropped["target not in the EDGAR submissions index"] += 1
                continue
            g_s, g_t = grades[start["adsh"]], grades[target["adsh"]]
            p19 = members(g_s) >= 4 and members(g_t) < members(g_s) / 2
            sp = start["period"]
            window_open = (date(int(sp[:4]), int(sp[4:6]), int(sp[6:])) - timedelta(days=30)).isoformat()
            rows[split].append({
                "episode_id": f"{co['cik']}-{q}", "split": split, "universe": co["universe"], "company": co["name"],
                "cik": co["cik"], "group": co["group"], "quarter_end": q,
                "start_adsh": start["adsh"], "start_form": start["form"], "start_period": start["period"],
                "target_adsh": target["adsh"], "target_form": target["form"], "target_period": target["period"],
                "window_open": window_open, "cutoff": ref.accepted,
                "target_level": g_t["level"], "graded_level": "L3" if p19 else g_t["level"], "p19_downgrade": int(p19),
                "start_members": members(g_s), "target_members": members(g_t),
                "target_coverage_itemised": g_t["coverage_itemised"], "company_level": co["level"],
            })
        print(f"{co['universe']:4s} {co['name'][:30]:30s} dev {sum(r['cik'] == co['cik'] for r in rows['dev']):2d}  "
              f"test {sum(r['cik'] == co['cik'] for r in rows['test']):2d}", flush=True)

    for split, rs in rows.items():
        with open(ROOT / "manifests" / f"{split}.csv", "w", encoding="utf-8", newline="") as f:
            f.write(f"# status: {gate_status()}; {split} episodes built by scripts/build_splits.py from universe_v1.json"
                    f"{' and manifests/generalisation.csv' if split == 'test' else ''}\n")
            w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
            w.writeheader()
            w.writerows(sorted(rs, key=lambda r: (r["universe"], r["company"], r["quarter_end"])))
    print("\n=== episodes ===")
    for split, rs in rows.items():
        for uni in ("ai25", "gen"):
            sub = [r for r in rs if r["universe"] == uni]
            if sub:
                print(f"{split:4s} {uni:4s} {len(sub):4d} episodes; graded level {dict(Counter(r['graded_level'] for r in sub))}; "
                      f"P19 downgrades {sum(r['p19_downgrade'] for r in sub)}")
    print("not built:", dict(dropped) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
