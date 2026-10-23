"""Baseline B0 — carry forward (DESIGN.md §9.3): the floor every tracker has to beat.

No reading at all. The ledger at the end of quarter t+1 is the last report's debt, minus the bonds
that reached their due date. Two choices make it a fair floor rather than a straw man:

* **The opening ledger is the last report itemised finely enough for the episode's level**, not
  blindly the previous one. Intel's 10-Qs itemise almost nothing (P19, P23), so carrying a 10-Q
  forward would leave B0 with no bonds and a 10-K quarter scored at zero. B0 instead walks back
  (at most 4 reports, 15 months) to the last report graded at that level or finer. Which report
  it used is recorded per episode.
* **Maturity sweep by year.** Most members give only a maturity *year*, so a bond is swept when
  its year is before the target quarter's year. A bond due in the target year is kept — it may or
  may not have matured by the quarter end, and B0 does not guess.

Totals (L3) are the opening report's total debt minus the swept bonds' USD amounts; the current
portion and maturity ladder are carried unchanged. Grading side only (it reads the answer key).
"""

from __future__ import annotations

from datetime import date

from ..answer_key import grading_level
from ..grader import offering_amount, principal_of, truth_totals

LEVEL_RANK = {"L3": 0, "L2": 1, "L1": 2}
LEDGER_KINDS = {"bond", "offering", "facility", "other"}


def _months(a: str, b: str) -> int:
    da, db = date(int(a[:4]), int(a[4:6]), 1), date(int(b[:4]), int(b[4:6]), 1)
    return (db.year - da.year) * 12 + db.month - da.month


def _detail(record: dict, level: str) -> float:
    g = grading_level(record)
    return g["coverage_itemised"] if level == "L1" else g["coverage_itemised"] + g["coverage_offerings"]


def opening_report(reports: list[dict], start_adsh: str, level: str, records: dict) -> tuple[dict, str]:
    """The record B0 carries forward, and a note on how it was chosen: the start report if it is
    graded at the episode's level; otherwise, of the reports in the last 15 months (at most 4 back),
    the one that itemises the most of its debt. Intel's FY2023 10-K itemises 79% — just under
    the L1 bar — and is still far better to carry forward than its 10-Qs, which itemise ~1%."""
    i = next(k for k, r in enumerate(reports) if r["adsh"] == start_adsh)
    start = reports[i]
    if LEVEL_RANK[grading_level(records[start_adsh])["level"]] >= LEVEL_RANK[level]:
        return records[start_adsh], "start report"
    best, best_back = None, 0
    for back in range(1, 5):
        if i - back < 0 or _months(reports[i - back]["period"], start["period"]) > 15:
            break
        r = reports[i - back]
        if best is None or _detail(records[r["adsh"]], level) > _detail(records[best["adsh"]], level):
            best, best_back = r, back
    if best is not None and _detail(records[best["adsh"]], level) > _detail(records[start_adsh], level):
        return records[best["adsh"]], f"walked back {best_back} report(s) to {best['form']} {best['period']}"
    return records[start_adsh], "start report (no better-itemised report within 15 months)"


def carry_forward(opening: dict, target_period: str) -> dict:
    target_year = int(target_period[:4])
    instruments, swept_usd, swept = [], 0.0, 0
    for i in opening["instruments"]:
        if not i["outstanding"] or i["klass"] not in LEDGER_KINDS:
            continue
        if i.get("maturity_year") and i["maturity_year"] < target_year:
            swept += 1
            swept_usd += i.get("amount_usd") or 0.0
            continue
        if i["klass"] == "offering":
            p, _, cur = offering_amount(i)   # what is left of the deal, as the key measures it
        else:
            (p, _), cur = principal_of(i), i.get("currency") or "USD"
        instruments.append({"kind": i["klass"], "currency": cur, "principal": p,
                            "coupon_pct": i.get("rate"), "maturity_year": i.get("maturity_year"),
                            "issued": i.get("issued"), "amount_usd": i.get("amount_usd"),
                            "source": {"adsh": opening["adsh"], "member": i["member"]}})
    totals = dict(truth_totals(opening))
    if "total_debt" in totals:
        totals["total_debt"] -= swept_usd
    return {"instruments": instruments, "totals": totals,
            "meta": {"baseline": "B0 carry-forward", "opening_adsh": opening["adsh"], "swept": swept}}
