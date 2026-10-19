"""Week 1: re-run feasibility check F1 (match instruments across consecutive reports) on the dev split.

Week 0 measured F1 at 83% (489/588) on test-window episodes with a regex on member names — inside
the 70–90% "partial" band, with five named causes (P17–P21). Week 1 built the fixes into the
member parser (labels, number words, glued years, P17 tolerance) and the matcher (name → label →
key → year+amount, unambiguous only). This script measures both methods on the **dev** split, so
the fixes are tuned and judged on dev and test stays untouched.

Two denominators are reported, both over instruments outstanding in the start report:
  raw       every instrument (comparable with the Week 0 number);
  adjusted  minus unmatched instruments due by the target's year (they plausibly matured, which
            is a real change, not a matching failure).
Populations: all dev AI-universe episodes, and the episodes graded L1 at both ends.

Pass line (set in Week 0, docs/feasibility.md): >= 90% of instruments match unambiguously.

Usage:  python scripts/f1_matching.py [dev|test]
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from ai_debt_tracker import config
from ai_debt_tracker.eval.answer_key import AnswerKey, grading_level
from ai_debt_tracker.ledger.matcher import match
from review_universe import extracted_periods

ROOT = Path(__file__).resolve().parents[1]
SPLIT = sys.argv[1] if len(sys.argv) > 1 else "dev"
TRACKED = ("bond", "facility", "other", "offering")


def spike_method(a: list[dict], b: list[dict]) -> int:
    """Week 0's rule: same member name, else same (tagged rate, last 20xx year in the member name)."""
    names_b = {x["member"] for x in b}
    def k(x):
        ys = re.findall(r"(20[2-6]\d)", x["member"])
        return (round(x["rate"], 2), int(ys[-1])) if x.get("rate") is not None and ys else None
    keys_b = {k(x) for x in b if k(x)}
    return sum(1 for x in a if x["member"] in names_b or (k(x) and k(x) in keys_b))


def main() -> int:
    with open(ROOT / "manifests" / f"{SPLIT}.csv", encoding="utf-8") as f:
        eps = [r for r in csv.DictReader(line for line in f if not line.startswith("#")) if r["universe"] == "ai25"]
    ak = AnswerKey(extracted_periods(), {int(r["cik"]) for r in eps})
    tot = {pop: Counter() for pop in ("all", "L1-both")}
    details, misses = [], Counter()
    for e in eps:
        recs = [ak.filing_record(e[k]) for k in ("start_adsh", "target_adsh")]
        a, b = ([i for i in r["instruments"] if i["outstanding"] and i["klass"] in TRACKED] for r in recs)
        if not a:
            continue
        r = match(a, b)
        target_year = int(e["target_period"][:4])
        matured = [i for i in r.unmatched_a if a[i].get("maturity_year") and a[i]["maturity_year"] <= target_year]
        old = spike_method(a, b)
        pops = ["all"] + (["L1-both"] if grading_level(recs[0])["level"] == "L1" and e["graded_level"] == "L1" else [])
        for pop in pops:
            t = tot[pop]
            t["episodes"] += 1
            t["n_t"] += len(a)
            t["matched_new"] += len(r.pairs)
            t["matched_old"] += old
            t["matured_unmatched"] += len(matured)
            t["ambiguous"] += len(r.ambiguous_a)
            for _, _, s in r.pairs:
                t[f"stage:{s}"] += 1
        for i in r.unmatched_a:
            if i not in matured:
                misses[(e["company"], a[i]["klass"])] += 1
        details.append({"episode": e["episode_id"], "company": e["company"], "n_t": len(a), "matched": len(r.pairs),
                        "spike_method": old, "by_stage": r.by_stage(), "matured_unmatched": len(matured),
                        "unmatched": [a[i]["member"] for i in r.unmatched_a],
                        "new_in_target": [b[j]["member"] for j in r.unmatched_b]})

    out = config.data_dir() / "week1"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"f1_{SPLIT}.json").write_text(json.dumps({"totals": {k: dict(v) for k, v in tot.items()}, "episodes": details}, indent=1))
    for pop, t in tot.items():
        if not t["episodes"]:
            continue
        adj = t["n_t"] - t["matured_unmatched"]
        print(f"[{SPLIT} / {pop}] {t['episodes']} episodes, {t['n_t']} instruments at t")
        print(f"   Week 0 method : {t['matched_old']}/{t['n_t']} = {t['matched_old'] / t['n_t']:.1%}")
        print(f"   new matcher   : {t['matched_new']}/{t['n_t']} = {t['matched_new'] / t['n_t']:.1%} raw;  "
              f"{t['matched_new']}/{adj} = {t['matched_new'] / adj:.1%} excluding {t['matured_unmatched']} plausibly matured")
        print(f"   by stage      : {{{', '.join(f'{k[6:]}: {v}' for k, v in sorted(t.items()) if k.startswith('stage:'))}}}; "
              f"ambiguous left unmatched: {t['ambiguous']}")
    print("largest unmatched (not matured), by company and class:", misses.most_common(8))
    return 0


if __name__ == "__main__":
    sys.exit(main())
