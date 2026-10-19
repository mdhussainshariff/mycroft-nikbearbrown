"""Match debt instruments between two lists — two reports, or a ledger and a report (DESIGN.md P3).

Plain code, deterministic, and conservative: a pair is made only when it is unambiguous at that
stage, and everything left over is returned, never dropped. Stages, strongest first:

1. **same member name** — the filer kept its own identifier;
2. **same label** — renamed member, same human text (case, punctuation and "[Member]" ignored);
3. **same key** — (currency, coupon, maturity year), coupons equal within the P17 rounding
   tolerance, and exactly one candidate on each side;
4. **same maturity year and amount** — for instruments without a coupon (term loans, some
   10-Qs), face or carrying amount within 1%, exactly one candidate on each side.

Instruments are dicts with any of: member, label, currency, rate, maturity_year, face, carrying.
Used by the feasibility re-run now, and by the merge node and the grader later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parsers import rates_match


@dataclass
class MatchResult:
    pairs: list[tuple[int, int, str]] = field(default_factory=list)   # (index in a, index in b, stage)
    unmatched_a: list[int] = field(default_factory=list)
    unmatched_b: list[int] = field(default_factory=list)
    ambiguous_a: list[int] = field(default_factory=list)               # had > 1 candidate at some stage

    def by_stage(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for _, _, s in self.pairs:
            out[s] = out.get(s, 0) + 1
        return out


def norm_label(label: str | None) -> str | None:
    if not label:
        return None
    t = re.sub(r"\[member\]|\bmember\b", " ", label.lower())
    t = re.sub(r"[^a-z0-9.%]+", " ", t)
    return re.sub(r"\s+", " ", t).strip() or None


def norm_name(member: str | None) -> str | None:
    if not member:
        return None
    return re.sub(r"(member)+$", "", re.sub(r"[^a-z0-9]", "", member.lower())) or None


def _amount(x: dict) -> float | None:
    return x.get("face") or x.get("carrying")


def _close(a: float | None, b: float | None, tol: float = 0.01) -> bool:
    return bool(a and b) and abs(a - b) <= tol * max(abs(a), abs(b))


def match(a: list[dict], b: list[dict]) -> MatchResult:
    res = MatchResult()
    free_a, free_b = set(range(len(a))), set(range(len(b)))
    ambiguous = set()

    def take(i, j, stage):
        res.pairs.append((i, j, stage))
        free_a.discard(i)
        free_b.discard(j)

    # 1. member name
    names_b = {}
    for j in sorted(free_b):
        names_b.setdefault(b[j].get("member"), []).append(j)
    for i in sorted(free_a):
        js = [j for j in names_b.get(a[i].get("member"), []) if j in free_b]
        if a[i].get("member") and len(js) == 1:
            take(i, js[0], "name")
    # 1b. the same name up to case, punctuation and a doubled "Member" suffix
    #     (Broadcom `A2017SeniorNotesMember` vs `A2017SeniorNotes`; Super Micro `E.SUNBank…` vs `ESUNBank…`)
    for i in sorted(free_a):
        na = norm_name(a[i].get("member"))
        js = [j for j in free_b if na and norm_name(b[j].get("member")) == na]
        if len(js) == 1:
            take(i, js[0], "name")

    # 2. label
    for i in sorted(free_a):
        la = norm_label(a[i].get("label"))
        if not la:
            continue
        js = [j for j in free_b if norm_label(b[j].get("label")) == la]
        if len(js) == 1:
            take(i, js[0], "label")
        elif len(js) > 1:
            ambiguous.add(i)

    # 3. key, unique on both sides
    def key_hits(x, pool, other):
        return [k for k in pool if other[k].get("rate") is not None and x.get("rate") is not None
                and rates_match(x["rate"], other[k]["rate"])
                and x.get("maturity_year") and x.get("maturity_year") == other[k].get("maturity_year")
                and (x.get("currency") or "USD") == (other[k].get("currency") or "USD")]
    for i in sorted(free_a):
        js = key_hits(a[i], free_b, b)
        if len(js) == 1 and len(key_hits(b[js[0]], free_a, a)) == 1:
            take(i, js[0], "key")
        elif len(js) > 1:
            ambiguous.add(i)

    # 4. maturity year + amount, unique on both sides
    def amt_hits(x, pool, other):
        return [k for k in pool if x.get("maturity_year") and x.get("maturity_year") == other[k].get("maturity_year")
                and _close(_amount(x), _amount(other[k]))]
    for i in sorted(free_a):
        js = amt_hits(a[i], free_b, b)
        if len(js) == 1 and len(amt_hits(b[js[0]], free_a, a)) == 1:
            take(i, js[0], "year+amount")
        elif len(js) > 1:
            ambiguous.add(i)

    res.unmatched_a = sorted(free_a)
    res.unmatched_b = sorted(free_b)
    res.ambiguous_a = sorted(ambiguous & free_a)
    return res
