"""Readability, hedging, forward-looking density, and quarter-to-quarter tone shift."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from ecis.db.init_db import get_connection

_HEDGE = re.compile(
    r"(?i)\b(we believe|approximately|subject to|may|could|might|possibly|"
    r"we think|it appears|somewhat|around)\b"
)
_DEFINITE = re.compile(
    r"(?i)\b(we will|we expect|guidance is|we are raising|we are lowering|"
    r"we reaffirm|outlook is|we now expect)\b"
)
_FORWARD = re.compile(
    r"(?i)\b(will|expect|outlook|guidance|next quarter|full year|going forward|"
    r"upcoming|forecast|intend|plan to)\b"
)
_BACKWARD = re.compile(
    r"(?i)\b(last quarter|year over year|we reported|we delivered|was|were|"
    r"compared to|prior year)\b"
)
_WORD = re.compile(r"[A-Za-z']+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text or "")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _syllables(word: str) -> int:
    w = word.lower()
    vowels = re.findall(r"[aeiouy]+", w)
    n = max(len(vowels), 1)
    if w.endswith("e") and n > 1:
        n -= 1
    return n


def flesch_kincaid(text: str) -> float:
    words = _words(text)
    sents = _sentences(text) or [text]
    if not words:
        return 0.0
    syll = sum(_syllables(w) for w in words)
    return round(0.39 * (len(words) / len(sents)) + 11.8 * (syll / len(words)) - 15.59, 3)


def gunning_fog(text: str) -> float:
    words = _words(text)
    sents = _sentences(text) or [text]
    if not words:
        return 0.0
    complex_n = sum(1 for w in words if _syllables(w) >= 3)
    return round(0.4 * ((len(words) / len(sents)) + 100 * (complex_n / len(words))), 3)


def hedging_index(text: str) -> float:
    hedges = len(_HEDGE.findall(text or ""))
    definite = len(_DEFINITE.findall(text or ""))
    denom = hedges + definite
    if denom == 0:
        return 0.0
    return round(hedges / denom, 4)


def fls_density(text: str) -> float:
    fwd = len(_FORWARD.findall(text or ""))
    back = len(_BACKWARD.findall(text or ""))
    denom = fwd + back
    if denom == 0:
        return 0.0
    return round(fwd / denom, 4)


def ks_statistic(a: list[float], b: list[float]) -> float:
    """Two-sample KS statistic without scipy."""
    if not a or not b:
        return 0.0
    sa, sb = sorted(a), sorted(b)
    values = sorted(set(sa + sb))
    i = j = 0
    na, nb = len(sa), len(sb)
    d = 0.0
    for v in values:
        while i < na and sa[i] <= v:
            i += 1
        while j < nb and sb[j] <= v:
            j += 1
        d = max(d, abs(i / na - j / nb))
    return d


def score_text(text: str) -> dict[str, float]:
    return {
        "flesch_kincaid": flesch_kincaid(text),
        "gunning_fog": gunning_fog(text),
        "hedging_index": hedging_index(text),
        "fls_density": fls_density(text),
    }


def link_linguistics(ticker: str | None = None) -> dict[str, Any]:
    conn = get_connection("signals")
    query = "SELECT signal_id, ticker, transcript_date, supporting_quote, confidence_raw FROM signals"
    params: list[str] = []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.upper())
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["ticker"], str(row["transcript_date"])[:10])].append(row)

    prior_conf: dict[str, list[float]] = {}
    n = 0
    for (sym, day), group in sorted(grouped.items()):
        blob = " ".join(r.get("supporting_quote") or "" for r in group)
        scores = score_text(blob)
        prev = prior_conf.get(sym, [])
        curr = [float(r.get("confidence_raw") or 0.0) for r in group]
        shift = ks_statistic(prev, curr) if prev else 0.0
        prior_conf[sym] = curr
        for row in group:
            conn.execute(
                """UPDATE signals SET flesch_kincaid=?, gunning_fog=?, hedging_index=?,
                   fls_density=?, tone_shift=? WHERE signal_id=?""",
                (
                    scores["flesch_kincaid"],
                    scores["gunning_fog"],
                    scores["hedging_index"],
                    scores["fls_density"],
                    shift,
                    row["signal_id"],
                ),
            )
            n += 1
    conn.commit()
    conn.close()
    return {"labelled": n}
