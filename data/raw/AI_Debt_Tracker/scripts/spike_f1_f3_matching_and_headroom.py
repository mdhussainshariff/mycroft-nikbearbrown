"""Feasibility spike F1 (match bonds across consecutive reports) and F3 (headroom over carry-forward).

For each L1 company in the AI universe: take its last 3 10-Q/10-K filed by 2026-09-30, pull its
per-instrument debt facts from the SEC monthly Financial Statement and Notes data, and compare
consecutive reports (2 transitions per company).
Outputs spike_episodes.json for the F2 announcement check.

Usage:
    python scripts/spike_f1_f3_matching_and_headroom.py
Downloads ~10 monthly notes zips (~50 MB each) into $AI_DEBT_DATA/spike/fsn. Results of the
2026-10-16 run are recorded in docs/feasibility.md.
"""

import csv
import io
import json
import os
import re
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import _localenv  # noqa: F401  (loads the gitignored .env)

csv.field_size_limit(10**9)
UA = {"User-Agent": f"{os.environ.get('EDGAR_NAME', 'ai-debt-tracker-spike')} {os.environ.get('EDGAR_EMAIL', '')}".strip()}
ROOT = Path(__file__).resolve().parent.parent
HERE = Path(os.environ.get("AI_DEBT_DATA", ROOT / "data")) / "spike"
CACHE = HERE / "fsn"
CACHE.mkdir(parents=True, exist_ok=True)
UNIVERSE = json.loads((ROOT / "docs" / "archive" / "universe_draft.json").read_text())["companies"]
L1 = [c for c in UNIVERSE if c["grading_level"] == "L1"]
BALANCE_TAGS = {
    "LongTermDebt", "DebtInstrumentCarryingAmount", "LongTermDebtGross", "LongTermDebtNoncurrent",
    "LongTermDebtCurrent", "DebtInstrumentFaceAmount", "SeniorNotes", "ConvertibleNotesPayable",
    "LongTermLineOfCredit", "LineOfCredit", "SecuredDebt", "UnsecuredDebt", "NotesPayable",
    "DebtCurrent", "LongTermNotesPayable", "DebtInstrumentUnamortizedDiscountPremiumAndDebtIssuanceCostsNet",
}


def get(url):
    for t in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if t == 2:
                raise
            time.sleep(3)


# 1. last three reports per company (filed by 2026-09-30)
reports = {}
for c in L1:
    rec = json.loads(get(f"https://data.sec.gov/submissions/CIK{c['cik']:010d}.json"))["filings"]["recent"]
    rows = [(rec["filingDate"][i], rec["accessionNumber"][i], rec["form"][i], rec["reportDate"][i])
            for i in range(len(rec["form"])) if rec["form"][i] in ("10-Q", "10-K") and rec["filingDate"][i] <= "2026-09-30"]
    reports[c["cik"]] = sorted(rows)[-3:]
    time.sleep(0.15)
months = sorted({r[0][:7].replace("-", "_") for rs in reports.values() for r in rs})
print("FS&N months needed:", months)

# 2. per-instrument facts from FS&N
wanted = {r[1]: (cik, r) for cik, rs in reports.items() for r in rs}
inst = defaultdict(lambda: defaultdict(dict))  # adsh -> member -> {"present": bool, "rate": x, "face": y, "maturity": d}
found_adsh = set()
for m in months:
    path = CACHE / f"{m}_notes.zip"
    if not path.exists():
        path.write_bytes(get(f"https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets/{m}_notes.zip"))
    z = zipfile.ZipFile(path)

    def rows(name):
        with z.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, "utf-8", errors="ignore"), delimiter="\t")

    period = {}
    for r in rows("sub.tsv"):
        if r["adsh"] in wanted:
            period[r["adsh"]] = r["period"]
            found_adsh.add(r["adsh"])
    if not period:
        continue
    dims = {}
    for r in rows("dim.tsv"):
        mm = re.search(r"DebtInstrument=([^;]+)", r["segments"])
        if mm:
            dims[r["dimhash"]] = mm.group(1)
    for r in rows("num.tsv"):
        a = r["adsh"]
        if a not in period or r["dimh"] not in dims:
            continue
        mem = dims[r["dimh"]]
        d = inst[a][mem]
        tag = r["tag"]
        try:
            v = float(r["value"])
        except ValueError:
            continue
        if tag == "DebtInstrumentInterestRateStatedPercentage":
            d["rate"] = round(v * 100 if v < 1 else v, 4)
        if tag == "DebtInstrumentFaceAmount":
            d["face"] = max(d.get("face", 0), v)
        if tag in BALANCE_TAGS and r["ddate"] == period[a] and r["qtrs"] == "0" and v > 0:
            d["present"] = True
    for r in rows("txt.tsv"):
        if r["adsh"] in period and r["tag"] == "DebtInstrumentMaturityDate" and r.get("dimh") in dims:
            inst[r["adsh"]][dims[r["dimh"]]]["maturity"] = r.get("value", "")
    print(f"  {m}: {len(period)} target filings parsed")


def year_of(member, d):
    if d.get("maturity"):
        mm = re.search(r"(20\d\d)", d["maturity"])
        if mm:
            return int(mm.group(1))
    ys = re.findall(r"(20[2-6]\d)", member)
    return int(ys[-1]) if ys else None


def key(member, d):
    y = year_of(member, d)
    return (d.get("rate"), y) if d.get("rate") is not None and y else None


# 3. compare consecutive reports
episodes, stats = [], defaultdict(int)
for cik, rs in reports.items():
    name = next(c["name"] for c in L1 if c["cik"] == cik)
    for (f0, a0, form0, p0), (f1, a1, form1, p1) in zip(rs, rs[1:]):
        if a0 not in found_adsh or a1 not in found_adsh:
            stats["missing_from_fsn"] += 1
            continue
        s0 = {m: d for m, d in inst[a0].items() if d.get("present")}
        s1 = {m: d for m, d in inst[a1].items() if d.get("present")}
        if not s0 and not s1:
            stats["no_instrument_facts"] += 1
            continue
        same_name = set(s0) & set(s1)
        added = set(s1) - set(s0)
        removed = set(s0) - set(s1)
        # F1: of add/remove pairs, how many are just renames (same rate + maturity year)?
        k_removed = {key(m, s0[m]): m for m in removed if key(m, s0[m])}
        renames = {m for m in added if key(m, s1[m]) and key(m, s1[m]) in k_removed}
        real_added = added - renames
        real_removed = removed - {k_removed[key(m, s1[m])] for m in renames}
        # F3: carry-forward is wrong unless every removal is a scheduled maturity
        p1_year = int(p1[:4])
        unexplained_removed = {m for m in real_removed if not (year_of(m, s0[m]) and year_of(m, s0[m]) <= p1_year)}
        b0_wrong = bool(real_added or unexplained_removed)
        stats["episodes"] += 1
        stats["b0_wrong"] += b0_wrong
        stats["instruments_t"] += len(s0)
        stats["matched_by_name"] += len(same_name)
        stats["matched_by_key"] += len(renames)
        episodes.append({
            "company": name, "cik": cik, "from": {"period": p0, "filed": f0, "adsh": a0}, "to": {"period": p1, "filed": f1, "adsh": a1},
            "n_t": len(s0), "n_t1": len(s1), "added": sorted(real_added), "removed": sorted(real_removed),
            "added_detail": {m: s1[m] for m in real_added}, "removed_detail": {m: s0[m] for m in real_removed},
            "renames": sorted(renames), "b0_wrong": b0_wrong,
        })
        print(f"{name:20s} {p0}->{p1}: t={len(s0):3d} t+1={len(s1):3d} same-name={len(same_name):3d} "
              f"renamed={len(renames):2d} added={len(real_added):2d} removed={len(real_removed):2d} carry-forward {'WRONG' if b0_wrong else 'ok'}")

print("\n=== summary ===")
for k, v in stats.items():
    print(f"{k}: {v}")
if stats["instruments_t"]:
    print(f"F1 instruments still present next report matched by name or key: "
          f"{(stats['matched_by_name'] + stats['matched_by_key'])}/{stats['instruments_t']}")
if stats["episodes"]:
    print(f"F3 carry-forward wrong in {stats['b0_wrong']}/{stats['episodes']} episodes")
(HERE / "spike_episodes.json").write_text(json.dumps(episodes, indent=1, default=str))
