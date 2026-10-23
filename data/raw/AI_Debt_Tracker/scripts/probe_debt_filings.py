"""Reproduce the debt-filing counts in DESIGN.md §3.2 and the answer-key levels in §3.3.

For every company in docs/archive/universe_draft.json, counts filings between START and END:
  8-K item 2.03 (creation of a direct financial obligation), 8-K item 1.01 (material definitive
  agreement), 424B2/424B5 prospectus supplements, FWP final term sheets, and 10-Q/10-K reports.
Then, for each company's latest 10-Q/10-K, counts the distinct members used on the debt
dimensions (DebtInstrumentAxis, LongtermDebtTypeAxis) — a quick read of how finely debt is tagged.

Usage:
    python scripts/probe_debt_filings.py [START] [END]      # defaults 2025-01-01 2026-09-30

Reads EDGAR_NAME / EDGAR_EMAIL from the environment for the SEC User-Agent.
"""

import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import _localenv  # noqa: F401  (loads the gitignored .env)

ROOT = Path(__file__).resolve().parent.parent
START = sys.argv[1] if len(sys.argv) > 1 else "2025-01-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-09-30"
UA = {"User-Agent": f"{os.environ.get('EDGAR_NAME', 'ai-debt-tracker-probe')} {os.environ.get('EDGAR_EMAIL', '')}".strip()}
DEBT_AXES = ("us-gaap:DebtInstrumentAxis", "us-gaap:LongtermDebtTypeAxis")


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def debt_members(cik, rec):
    """Distinct members on the debt axes in the latest 10-Q/10-K."""
    i = next(k for k, f in enumerate(rec["form"]) if f in ("10-K", "10-Q"))
    acc, doc = rec["accessionNumber"][i], rec["primaryDocument"][i]
    html = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}").decode("utf-8", "ignore")
    found = {}
    for axis in DEBT_AXES:
        members = set(re.findall(rf'dimension="{re.escape(axis)}"[^>]*>\s*([\w:.-]+)\s*<', html))
        found[axis.split(":")[1]] = len(members)
    return f"{rec['form'][i]} {rec['filingDate'][i]}", found


universe = json.loads((ROOT / "docs" / "archive" / "universe_draft.json").read_text())["companies"]
print(f"window {START} .. {END}\n")
print(f"{'company':20s} {'8-K 2.03':>8s} {'8-K 1.01':>8s} {'424B2/5':>7s} {'FWP':>4s} {'10-Q/K':>6s}   latest report       DebtInstrument  LongtermDebtType")
totals = Counter()
for co in universe:
    cik = co["cik"]
    try:
        rec = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))["filings"]["recent"]
        c = Counter()
        for form, date, items in zip(rec["form"], rec["filingDate"], rec.get("items", [""] * len(rec["form"]))):
            if not (START <= date <= END):
                continue
            if form in ("8-K", "8-K/A"):
                its = set((items or "").split(","))
                c["2.03"] += "2.03" in its
                c["1.01"] += "1.01" in its
            elif form in ("424B2", "424B5"):
                c["424B"] += 1
            elif form == "FWP":
                c["FWP"] += 1
            elif form in ("10-Q", "10-K"):
                c["periodic"] += 1
        totals.update(c)
        time.sleep(0.15)
        latest, members = debt_members(cik, rec)
        print(f"{co['name']:20s} {c['2.03']:>8d} {c['1.01']:>8d} {c['424B']:>7d} {c['FWP']:>4d} {c['periodic']:>6d}   "
              f"{latest:19s} {members['DebtInstrumentAxis']:>14d} {members['LongtermDebtTypeAxis']:>17d}")
    except Exception as ex:  # noqa: BLE001
        print(f"{co['name']:20s} ERROR {type(ex).__name__}: {ex}")
    time.sleep(0.15)
print(f"{'TOTAL':20s} {totals['2.03']:>8d} {totals['1.01']:>8d} {totals['424B']:>7d} {totals['FWP']:>4d} {totals['periodic']:>6d}")
