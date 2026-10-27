"""Scorer: query signals+outcomes and compute per-reader and aggregate metrics."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from ecis.db.init_db import get_connection
from ecis.scoring.metrics import (
    brier_score,
    expected_calibration_error,
    murphy_decomposition,
    skill_score,
)

logger = logging.getLogger(__name__)


def _fetch_scored_data(
    ticker: str | None = None,
    source_method: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch joined signals+outcomes data."""
    conn_s = get_connection("signals")
    conn_o = get_connection("outcomes")

    query = "SELECT signal_id, ticker, direction, confidence_raw, source_method, llm_model, low_confidence, trend, decay_profile, speaker_role FROM signals"
    params: list[Any] = []
    conditions = []

    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker)
    if source_method:
        conditions.append("source_method = ?")
        params.append(source_method)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    try:
        signals = conn_s.execute(query, params).fetchall()
    except Exception:
        query = query.replace(", llm_model, low_confidence, trend, decay_profile, speaker_role", "")
        signals = conn_s.execute(query, params).fetchall()
    conn_s.close()

    results = []
    for sig in signals:
        if "low_confidence" in sig.keys() and sig["low_confidence"]:
            continue
        try:
            outcomes = conn_o.execute(
                """SELECT horizon_days, correct, excess_return, reaction_magnitude,
                          sector_excess_return FROM outcomes WHERE signal_id = ?""",
                (sig["signal_id"],),
            ).fetchall()
        except Exception:
            outcomes = conn_o.execute(
                "SELECT horizon_days, correct, excess_return FROM outcomes WHERE signal_id = ?",
                (sig["signal_id"],),
            ).fetchall()

        for out in outcomes:
            if out["correct"] is not None:
                mag = out["reaction_magnitude"] if "reaction_magnitude" in out.keys() else None
                sector_ex = out["sector_excess_return"] if "sector_excess_return" in out.keys() else None
                results.append({
                    "signal_id": sig["signal_id"],
                    "ticker": sig["ticker"],
                    "direction": sig["direction"],
                    "confidence": sig["confidence_raw"],
                    "source_method": sig["source_method"],
                    "llm_model": sig["llm_model"] if "llm_model" in sig.keys() else None,
                    "trend": sig["trend"] if "trend" in sig.keys() else None,
                    "decay_profile": sig["decay_profile"] if "decay_profile" in sig.keys() else None,
                    "speaker_role": sig["speaker_role"] if "speaker_role" in sig.keys() else None,
                    "horizon_days": out["horizon_days"],
                    "correct": out["correct"],
                    "excess_return": sector_ex if sector_ex is not None else out["excess_return"],
                    "reaction_magnitude": mag,
                })

    conn_o.close()
    return results


def score_reader(
    source_method: str | None = None,
    ticker: str | None = None,
    horizon: int | None = None,
) -> dict[str, Any]:
    """Compute all metrics for a specific reader (or all if None)."""
    data = _fetch_scored_data(ticker=ticker, source_method=source_method)

    if horizon:
        data = [d for d in data if d["horizon_days"] == horizon]

    if not data:
        return {
            "source_method": source_method or "all",
            "ticker": ticker or "all",
            "horizon": horizon or "all",
            "n_samples": 0,
            "brier": None,
            "skill_score": None,
            "ece": None,
            "murphy": None,
        }

    confidences = [d["confidence"] for d in data]
    outcomes = [d["correct"] for d in data]

    bs = brier_score(confidences, outcomes)
    base_rate = sum(outcomes) / len(outcomes)
    ref_brier = base_rate * (1 - base_rate)
    ss = skill_score(bs, ref_brier)
    ece, ece_bins = expected_calibration_error(confidences, outcomes)
    murphy = murphy_decomposition(confidences, outcomes)
    excess = [d["excess_return"] for d in data if d.get("excess_return") is not None]
    ir = None
    if len(excess) >= 2:
        std = float(np.std(excess))
        if std > 0:
            ir = round(float(np.mean(excess) / std), 6)

    ci = None
    ir_ci = None
    if len(data) >= 5:
        from ecis.scoring.bootstrap import information_ratio_ci, paired_brier_skill

        ci = paired_brier_skill(confidences, outcomes)
        if excess:
            ir_ci = information_ratio_ci(excess)

    return {
        "source_method": source_method or "all",
        "ticker": ticker or "all",
        "horizon": horizon or "all",
        "n_samples": len(data),
        "base_rate": round(base_rate, 4),
        "brier": round(bs, 6),
        "skill_score": round(ss, 6),
        "ece": ece,
        "ece_bins": ece_bins,
        "murphy": murphy,
        "information_ratio": ir,
        "bootstrap": ci,
        "information_ratio_ci": ir_ci,
    }


def score_all_readers(
    ticker: str | None = None,
    horizon: int | None = None,
) -> list[dict[str, Any]]:
    """Score all reader types individually plus aggregate."""
    readers = ["keyword", "finbert", "llm", "finetuned_llm", "triangulated"]
    results = []

    for reader in readers:
        result = score_reader(source_method=reader, ticker=ticker, horizon=horizon)
        if result["n_samples"] > 0:
            results.append(result)

    aggregate = score_reader(source_method=None, ticker=ticker, horizon=horizon)
    aggregate["source_method"] = "aggregate"
    results.append(aggregate)

    return results


def score_by_llm_model(
    ticker: str | None = None,
    horizon: int | None = None,
) -> list[dict[str, Any]]:
    """Score signals grouped by llm_model alias (llama / mistral / qwen)."""
    from ecis.config.settings import settings

    data = _fetch_scored_data(ticker=ticker)
    if horizon:
        data = [d for d in data if d["horizon_days"] == horizon]

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in data:
        raw = row.get("llm_model") or ""
        alias = settings.model_alias(raw) if raw else "unknown"
        groups.setdefault(alias, []).append(row)

    results = []
    for alias, rows in sorted(groups.items()):
        confidences = [d["confidence"] for d in rows]
        outcomes = [d["correct"] for d in rows]
        bs = brier_score(confidences, outcomes)
        base_rate = sum(outcomes) / len(outcomes) if outcomes else 0.0
        ref_brier = base_rate * (1 - base_rate)
        ss = skill_score(bs, ref_brier)
        ece, _ = expected_calibration_error(confidences, outcomes)
        murphy = murphy_decomposition(confidences, outcomes)
        results.append({
            "llm_model": alias,
            "n_samples": len(rows),
            "brier": round(bs, 6),
            "skill_score": round(ss, 6),
            "ece": ece,
            "murphy": murphy,
        })
    return results


def score_by_trend(
    ticker: str | None = None,
    horizon: int | None = None,
) -> list[dict[str, Any]]:
    """Score signals grouped by retrospective trend label."""
    data = _fetch_scored_data(ticker=ticker)
    if horizon:
        data = [d for d in data if d["horizon_days"] == horizon]

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in data:
        label = row.get("trend") or "unlabelled"
        groups.setdefault(label, []).append(row)

    results = []
    for label, rows in sorted(groups.items()):
        confidences = [d["confidence"] for d in rows]
        outcomes = [d["correct"] for d in rows]
        bs = brier_score(confidences, outcomes)
        base_rate = sum(outcomes) / len(outcomes) if outcomes else 0.0
        ref_brier = base_rate * (1 - base_rate)
        ss = skill_score(bs, ref_brier)
        ece, _ = expected_calibration_error(confidences, outcomes)
        excess = [d["excess_return"] for d in rows if d.get("excess_return") is not None]
        ir = None
        if len(excess) >= 2:
            std = float(np.std(excess))
            if std > 0:
                ir = round(float(np.mean(excess) / std), 6)
        results.append({
            "trend": label,
            "n_samples": len(rows),
            "brier": round(bs, 6),
            "skill_score": round(ss, 6),
            "ece": ece,
            "information_ratio": ir,
        })
    return results


def score_by_decay(
    ticker: str | None = None,
    horizon: int | None = None,
) -> list[dict[str, Any]]:
    data = _fetch_scored_data(ticker=ticker)
    if horizon:
        data = [d for d in data if d["horizon_days"] == horizon]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in data:
        groups.setdefault(row.get("decay_profile") or "unlabelled", []).append(row)
    results = []
    for label, rows in sorted(groups.items()):
        confidences = [d["confidence"] for d in rows]
        outcomes = [d["correct"] for d in rows]
        bs = brier_score(confidences, outcomes)
        base_rate = sum(outcomes) / len(outcomes) if outcomes else 0.0
        ss = skill_score(bs, base_rate * (1 - base_rate))
        results.append({
            "decay_profile": label,
            "n_samples": len(rows),
            "brier": round(bs, 6),
            "skill_score": round(ss, 6),
        })
    return results


def print_scorecard(ticker: str | None = None, horizon: int | None = None) -> None:
    """Print a formatted scoring report."""
    results = score_all_readers(ticker=ticker, horizon=horizon)

    scope = f"Ticker: {ticker or 'ALL'} | Horizon: {horizon or 'ALL'} days"
    print(f"\n{'='*70}")
    print(f"  ECIS Scoring Report — {scope}")
    print(f"{'='*70}")
    print(f"  {'Reader':<15} {'N':>6} {'Brier':>8} {'Skill':>8} {'ECE':>8} {'Reliab':>8} {'Resol':>8}")
    print(f"  {'-'*15} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    for r in results:
        if r["n_samples"] == 0:
            continue
        murphy = r.get("murphy", {})
        print(
            f"  {r['source_method']:<15} {r['n_samples']:>6} "
            f"{r['brier']:>8.4f} {r['skill_score']:>8.4f} {r['ece']:>8.4f} "
            f"{murphy.get('reliability', 0):>8.4f} {murphy.get('resolution', 0):>8.4f}"
        )
        ci = r.get("bootstrap") or {}
        if ci.get("brier"):
            b = ci["brier"]
            s = ci["skill"]
            e = ci["ece"]
            print(
                f"    95% CI brier [{b['lo']:.4f}, {b['hi']:.4f}]  "
                f"skill [{s['lo']:.4f}, {s['hi']:.4f}]  "
                f"ece [{e['lo']:.4f}, {e['hi']:.4f}]"
            )

    trends = score_by_trend(ticker=ticker, horizon=horizon)
    labelled = [t for t in trends if t["n_samples"] > 0 and t["trend"] != "unlabelled"]
    if labelled:
        print(f"  {'Trend':<22} {'N':>6} {'Brier':>8} {'Skill':>8} {'IR':>8}")
        print(f"  {'-'*22} {'-'*6} {'-'*8} {'-'*8} {'-'*8}")
        for t in labelled:
            ir = t.get("information_ratio")
            ir_s = f"{ir:>8.4f}" if ir is not None else f"{'n/a':>8}"
            print(
                f"  {t['trend']:<22} {t['n_samples']:>6} "
                f"{t['brier']:>8.4f} {t['skill_score']:>8.4f} {ir_s}"
            )

    decays = [d for d in score_by_decay(ticker=ticker, horizon=horizon)
              if d["n_samples"] > 0 and d["decay_profile"] != "unlabelled"]
    if decays:
        print(f"  {'Decay':<22} {'N':>6} {'Brier':>8} {'Skill':>8}")
        print(f"  {'-'*22} {'-'*6} {'-'*8} {'-'*8}")
        for d in decays:
            print(
                f"  {d['decay_profile']:<22} {d['n_samples']:>6} "
                f"{d['brier']:>8.4f} {d['skill_score']:>8.4f}"
            )

    for role_row in score_by_speaker(ticker=ticker, horizon=horizon):
        if role_row["n_samples"] == 0:
            continue
        print(
            f"  role:{role_row['speaker_role']:<16} {role_row['n_samples']:>6} "
            f"{role_row['brier']:>8.4f} {role_row['skill_score']:>8.4f}"
        )

    for tier_row in score_by_confidence_tier(ticker=ticker, horizon=horizon):
        if tier_row["n_samples"] == 0:
            continue
        print(
            f"  tier:{tier_row['tier']:<16} {tier_row['n_samples']:>6} "
            f"{tier_row['brier']:>8.4f} {tier_row['skill_score']:>8.4f}"
        )

    print(f"{'='*70}\n")


def _group_metrics(rows: list[dict[str, Any]], key: str, label: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key) or "unknown"), []).append(row)
    results = []
    for name, items in sorted(groups.items()):
        confidences = [d["confidence"] for d in items]
        outcomes = [d["correct"] for d in items]
        bs = brier_score(confidences, outcomes)
        base_rate = sum(outcomes) / len(outcomes) if outcomes else 0.0
        ss = skill_score(bs, base_rate * (1 - base_rate))
        ece, _ = expected_calibration_error(confidences, outcomes)
        excess = [d["excess_return"] for d in items if d.get("excess_return") is not None]
        ir = None
        if len(excess) >= 2:
            std = float(np.std(excess))
            if std > 0:
                ir = round(float(np.mean(excess) / std), 6)
        results.append({
            label: name,
            "n_samples": len(items),
            "brier": round(bs, 6),
            "skill_score": round(ss, 6),
            "ece": ece,
            "information_ratio": ir,
        })
    return results


def score_by_speaker(ticker: str | None = None, horizon: int | None = None) -> list[dict[str, Any]]:
    data = _fetch_scored_data(ticker=ticker)
    if horizon:
        data = [d for d in data if d["horizon_days"] == horizon]
    return _group_metrics(data, "speaker_role", "speaker_role")


def score_by_confidence_tier(ticker: str | None = None, horizon: int | None = None) -> list[dict[str, Any]]:
    data = _fetch_scored_data(ticker=ticker)
    if horizon:
        data = [d for d in data if d["horizon_days"] == horizon]
    for row in data:
        c = row["confidence"]
        row["tier"] = "high" if c > 0.8 else "medium" if c >= 0.5 else "low"
    return _group_metrics(data, "tier", "tier")


def score_impact_weighted(ticker: str | None = None, horizon: int | None = None) -> dict[str, Any]:
    data = _fetch_scored_data(ticker=ticker)
    if horizon:
        data = [d for d in data if d["horizon_days"] == horizon]
    if not data:
        return {"n_samples": 0}
    weights = [max(float(d.get("reaction_magnitude") or 0.0), 1e-6) for d in data]
    total = sum(weights)
    confs = [d["confidence"] for d in data]
    outs = [d["correct"] for d in data]
    bs = float(np.average([(c - o) ** 2 for c, o in zip(confs, outs)], weights=weights))
    base = float(np.average(outs, weights=weights))
    ref = base * (1 - base)
    return {
        "n_samples": len(data),
        "weight_sum": round(total, 6),
        "brier": round(bs, 6),
        "skill_score": round(skill_score(bs, ref) if ref else 0.0, 6),
    }
