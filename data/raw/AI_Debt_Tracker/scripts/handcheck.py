"""Week 2: hand-check the answer key against the debt tables printed in 10 reports (DESIGN.md §11).

The answer key comes from XBRL tags. The check has to come from somewhere else, or it checks
nothing: here it is the **printed** debt table in the report's HTML, read as text.

  extract   for each chosen episode: fetch the target report, find the rows of its debt table
            (a coupon and a year on the same row, or a total-debt line), parse them into a draft
            transcription `manifests/handcheck/<episode>.json` with every source row kept beside it
  grade     grade each reviewed transcription *as a ledger* against the answer key at the episode's
            frozen level; a correct answer key and a correct grader agree on every row

The draft is a starting point. Each transcription is reviewed row by row against the raw table text
(`$AI_DEBT_DATA/week2/handcheck/<episode>.txt`) before grading, and the reviewer and any corrections
are written into the file. Amounts are read in the table's stated unit (millions, as printed).

Usage:
    python scripts/handcheck.py extract
    python scripts/handcheck.py grade
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from ai_debt_tracker import config
from ai_debt_tracker.edgar import ARCHIVE, load_filings
from ai_debt_tracker.eval.answer_key import AnswerKey
from ai_debt_tracker.eval.grader import grade_episode, truth_bonds, truth_totals, truth_units
from ai_debt_tracker.mcp_servers.edgar_pit_core import html_to_text
from ai_debt_tracker.sec import SecClient
from review_universe import extracted_periods

ROOT = Path(__file__).resolve().parents[1]
HC = ROOT / "manifests" / "handcheck"
RAW = config.data_dir() / "week2" / "handcheck"
EPISODES = ["1101239-2024-12-31", "1045810-2024-12-31", "1730168-2025-03-31", "723125-2025-06-30",
            "1769628-2025-06-30", "1341439-2025-06-30", "1108524-2025-06-30", "789019-2025-06-30",
            "1326801-2024-12-31", "1692819-2025-06-30"]
# Chosen after the calibration fixes and before any of them was read; graded once, nothing changed
# in response (AMD carries a combined member, Digital Realty number words and a subtotal).
HOLDOUT = ["2488-2025-03-31", "1297996-2025-06-30", "1640147-2025-06-30"]

RATE = re.compile(r"(\d{1,2}\.\d{1,4})\s*%")
YEAR = re.compile(r"\b(20[2-7]\d)\b")
NUM = re.compile(r"(?<![\w.])\(?\$?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\)?(?![\w%])")
CURRENCY = [("EUR", r"euro|€"), ("GBP", r"sterling|£|pound"), ("CHF", r"swiss|chf"), ("JPY", r"yen"),
            ("CAD", r"canadian|cad\b"), ("SGD", r"singapore"), ("AUD", r"australian")]


def episodes(ids: list[str] | None = None) -> dict:
    with open(ROOT / "manifests" / "dev.csv", encoding="utf-8") as f:
        rows = {e["episode_id"]: e for e in csv.DictReader(line for line in f if not line.startswith("#"))}
    return {k: rows[k] for k in (ids if ids is not None else EPISODES + HOLDOUT)}


COUPON_CELL = re.compile(r"^\(?(\d{1,2}\.\d{1,4})\s*%?\)?$")


def table_rows(html: str) -> list[str]:
    """Every <tr> as one line, cells joined by ' | ' — cells often hold <p>/<div>, which would
    otherwise break one row into many lines (Oracle, Nvidia, Microsoft)."""
    rows = []
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", html):
        cells = [" ".join(html_to_text(td).split()) for td in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
        cells = [c for c in cells if c and c not in ("$", "%", "€")]
        if cells:
            rows.append(" | ".join(cells))
    return rows


def coupon_of(row: str) -> float | None:
    m = RATE.search(row.split("|")[0]) or RATE.search(row)
    if m:
        return float(m.group(1))
    for cell in (c.strip() for c in row.split("|")[1:]):   # Salesforce prints the coupon in its own cell
        m = COUPON_CELL.match(cell)
        if m and 0 < float(m.group(1)) < 20:
            return float(m.group(1))
    return None


def debt_rows(rows: list[str]) -> list[str]:
    """Table rows that carry a coupon and a year on a note/bond/loan line, or name a debt total."""
    out = []
    for flat in rows:
        has_bond = (coupon_of(flat) is not None and YEAR.search(flat)
                    and re.search(r"note|bond|debenture|due|loan|debt", flat, re.I))
        has_total = re.search(r"total (long-term )?debt|long-term debt, net|total borrowings|total notes|"
                              r"total senior notes|long-term debt, including current", flat, re.I)
        if has_bond or has_total:
            out.append(flat)
    return out


def parse_row(row: str, scale: float) -> dict:
    label = row.split("|")[0]
    c = coupon_of(row)
    rate = re.match(r"(.*)", str(c)) if c is not None else None
    years = YEAR.findall(label) or YEAR.findall(row)
    nums = [n for n in NUM.findall(row.split("|", 1)[1] if "|" in row else "") if not re.fullmatch(r"20[2-7]\d", n)]
    amount = float(nums[0].replace(",", "")) * scale if nums else None
    cur = next((c for c, pat in CURRENCY if re.search(pat, row, re.I)), "USD")
    return {"coupon_pct": float(rate.group(1)) if rate else None, "maturity_year": int(years[-1]) if years else None,
            "principal": amount, "currency": cur, "row": row[:240]}


def extract() -> int:
    client = SecClient()
    HC.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    for ep_id, e in episodes().items():
        cik, adsh = int(e["cik"]), e["target_adsh"]
        ref = load_filings(client, cik)[adsh]
        html = client.get(ARCHIVE.format(cik=cik, acc_nodash=adsh.replace("-", "")) + ref.primary_document).decode("utf-8", "ignore")
        text = html_to_text(html)
        scale = 1e6 if re.search(r"in millions", text, re.I) else 1e3 if re.search(r"in thousands", text, re.I) else 1.0
        rows = debt_rows(table_rows(html))
        (RAW / f"{ep_id}.txt").write_text("\n".join(rows), encoding="utf-8")
        draft = {"episode": ep_id, "company": e["company"], "report": f"{e['target_form']} {e['target_period']}",
                 "accession": adsh, "level": e["graded_level"], "unit": scale, "status": "draft",
                 "instruments": [{"kind": "bond", **parse_row(r, scale)} for r in rows if coupon_of(r) is not None],
                 "totals_rows": [r[:240] for r in rows if coupon_of(r) is None]}
        path = HC / f"{ep_id}.json"
        if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("status") != "draft":
            print(f"{ep_id}: reviewed transcription exists, not overwritten")
            continue
        path.write_text(json.dumps(draft, indent=1), encoding="utf-8")
        print(f"{ep_id:22s} {e['company']:12s} {len(rows):3d} rows, {len(draft['instruments']):3d} bond rows, unit {scale:g}")
    return 0


FIRST_PASS = """The first grading of the calibration set agreed on **8 of 10**. Every disagreement was traced to
its cause, and each was a defect in the answer key or the grader, not in the printed report:

| # | Found on | Defect | Fix |
|---|---|---|---|
| P30 | Oracle 10-K | Repaid notes kept their original face amount tagged at the period end, with carrying amount 0; the key counted them as outstanding | An explicit zero balance wins; face at period end counts only when no balance is tagged |
| P31 | AMD | A member naming two bonds ("4.319% … Due 2028 And 4.212% … Due 2026") was read as a duplicate 4.319% 2028 bond | Members naming several coupons or maturities are deals, not bonds |
| P32 | Broadcom | Debt assumed in the VMware acquisition is tagged on a `BusinessAcquisition` axis, which the key discarded (56 facts, 10 notes) | The axis is descriptive, so the facts are kept |
| P33 | Broadcom | VMware's notes are named by due date (`May2025SeniorNotes`) and were read as issue-date deals | A month on or after the report's period end is a maturity; and one member is misspelt `SeniorNots` |
| P34 | Equinix | A Swiss franc note's label never names the currency and both its amounts are tagged in USD; the key called it a dollar bond | A currency counts as known only from the label or a foreign-unit face; otherwise it does not block a match |
| — | Microsoft | An offering's tagged face is the *original* deal size ($19.8 bn), not what is left ($7.93 bn) | Offerings are graded on their outstanding carrying amount |

These ten were used to find the fixes, so their 10 of 10 is a calibration, not an independent
accuracy estimate. That is what the **held-out** reports below are for: chosen before any of them
was read, graded once after every fix, and nothing changed in response to them."""


HOLDOUT_FINDINGS = """**What the held-out disagreement shows** (diagnosed, deliberately *not* fixed in Week 2 — fixing it
would turn the held-out set into a second calibration set; these are Week 3's first items):

| # | Found on | Defect | Proposed fix (Week 3, then a fresh held-out check) |
|---|---|---|---|
| P35 | Digital Realty 10-Q | The repaid £400 m 4.250% notes have no balance tag at all, only a face amount dated at the period end, so the key keeps them | The face-at-period-end fallback is unreliable on its own; require a balance tag, or a face tag in a report that tags no balances anywhere |
| P36 | Digital Realty 10-Q | The 1.875% exchangeable notes are dollar notes, but the filer tagged their face in euros, so the key's currency blocks the match | Prefer the carrying amount's unit when face and carrying units disagree, and treat the currency as unknown |
| P37 | Digital Realty 10-Q | Euro notes' face amounts are tagged as dollar translations; the key's principal is in a different currency from the printed one (4 of 20 agree) | Score principal only when the key's currency is known and equals the ledger's |

Identity matching held up on the held-out set — 27 of 29 printed bonds matched (AMD 5/5, Snowflake 2/2, Digital
Realty 20/22). Principal amounts on foreign-currency notes are the weak spot."""


def grade_one(ep_id: str, e: dict, ak) -> tuple[str, bool, list[str]]:
    t = json.loads((HC / f"{ep_id}.json").read_text(encoding="utf-8"))
    if t.get("status") == "draft":
        return f"| {ep_id} | {e['company']} | {t['report']} | {e['graded_level']} | — | — | — | — | not reviewed |", False, []
    target = ak.filing_record(e["target_adsh"])
    ledger = {"instruments": t["instruments"], "totals": t.get("totals", {})}
    g = grade_episode(target, ledger, e["graded_level"])
    tot = g["l3"]
    tot_ok = sum(v["ok"] for k, v in tot.items() if k in t.get("totals", {}))
    tot_n = sum(1 for k in tot if k in t.get("totals", {}))
    if e["graded_level"] == "L1":
        x = g["l1"]
        printed, key, matched = x["ledger"], x["truth"], x["matched"]
        stated = x["principal_scored"] - x["principal_unstated"]   # foreign notes printed only in USD
        ok = matched == key and x["extra"] == 0 and x["principal_ok"] == stated and tot_ok == tot_n
        detail = f"{matched} (principal {x['principal_ok']}/{stated}" + \
                 (f"; {x['covered_by_offering']} printed bonds = tagged offering totals" if x["covered_by_offering"] else "") + ")"
    elif e["graded_level"] == "L2":
        x = g["l2"]
        printed, key, matched = x["ledger"], x["truth"], x["matched"]
        ok = matched == key and tot_ok == tot_n
        detail = str(matched)
    else:
        printed = key = "—"
        ok = tot_n > 0 and tot_ok == tot_n
        detail = "—"
    notes = [f"- **{e['company']} {t['report']}** — {t['review']}"] if t.get("review") else []
    if not ok:
        x = g.get("l1", g.get("l2", {}))
        notes.append(f"- **{e['company']}**: disagreement — key members unmatched: {x.get('missed', [])[:8]}; "
                     f"printed rows unexplained: {x.get('extra', 0)}; totals: "
                     f"{ {k: (v['truth'], v['ledger']) for k, v in tot.items() if k in t.get('totals', {})} }")
    row = (f"| {ep_id} | {e['company']} | {t['report']} | {e['graded_level']} | {printed} | {key} | {detail} | "
           f"{tot_ok}/{tot_n} | {'**yes**' if ok else '**no**'} |")
    return row, ok, notes


def grade() -> int:
    eps, held = episodes(EPISODES), episodes(HOLDOUT)
    ak = AnswerKey(extracted_periods(), {int(e["cik"]) for e in list(eps.values()) + list(held.values())})
    head = ["| Episode | Company | Report | Level | Printed | Key | Matched | Totals within 2% | Agree? |",
            "|---|---|---|---|---|---|---|---|---|"]
    L = ["# Hand-check — the answer key against printed debt tables\n",
         "> Generated by `scripts/handcheck.py grade`. Each transcription (`manifests/handcheck/<episode>.json`) was "
         "read from the report's printed debt table, not from its XBRL tags, and graded *as a ledger* against the answer "
         "key. Agreement means the key, the grader and the printed report say the same thing.\n"]
    notes = []
    for title, group in (("Calibration set (DESIGN.md §11's 10 company-quarters)", eps), ("Held-out set", held)):
        rows, agree = [], 0
        for ep_id, e in group.items():
            row, ok, n = grade_one(ep_id, e, ak)
            rows.append(row)
            agree += ok
            notes += n
        L += [f"## {title}: {agree} of {len(group)} agree\n"]
        if group is eps:
            L += [FIRST_PASS + "\n"]
        L += head + rows + [""]
        if group is held:
            L += [HOLDOUT_FINDINGS + "\n"]
    L += ["## Review notes\n"] + notes
    gate_path = ROOT / "manifests" / "week2_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {}
    L += ["\n## Who checked\n",
          "Transcribed and reviewed by Claude (a model judgment, P8), from the printed tables; see each file's "
          "`reviewer` field. "
          + (f"**Accepted as the Week 2 check by {gate['cleared_by']} on {gate['date']}** "
             "(`manifests/week2_gate.json`).\n" if gate.get("status") == "CLEARED" else
             "Accepting this check is a gate for a named human (P4).\n")]
    (ROOT / "docs" / "handcheck.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(line for line in L if line.startswith("## ") or line.startswith("| 1") or line.startswith("| 2")
                    or line.startswith("| 7")))
    return 0


if __name__ == "__main__":
    sys.exit(extract() if (sys.argv[1:2] or ["grade"])[0] == "extract" else grade())
