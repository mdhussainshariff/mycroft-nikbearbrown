"""Grade pre-registered predictions against later extracted guidance."""

from __future__ import annotations

from typing import Any

from ecis.prediction.baselines import always_maintained, momentum
from ecis.prediction.features import build_feature_rows
from ecis.prediction.log import fill_actuals, list_predictions
from ecis.scoring.metrics import brier_score, expected_calibration_error, murphy_decomposition, skill_score


def _onehot_correct(predicted: str, actual: str, confidence: float) -> tuple[float, int]:
    return confidence, 1 if predicted == actual else 0


def _metrics(pairs: list[tuple[float, int]], label: str) -> dict[str, Any]:
    if not pairs:
        return {"name": label, "n": 0}
    confs = [p[0] for p in pairs]
    outs = [p[1] for p in pairs]
    bs = brier_score(confs, outs)
    base = sum(outs) / len(outs)
    ref = base * (1 - base)
    ece, _ = expected_calibration_error(confs, outs)
    return {
        "name": label,
        "n": len(pairs),
        "accuracy": round(base, 4),
        "brier": round(bs, 6),
        "skill_score": round(skill_score(bs, ref) if ref else 0.0, 6),
        "ece": ece,
        "murphy": murphy_decomposition(confs, outs),
    }


def score_predictions(ticker: str | None = None) -> dict[str, Any]:
    fill_actuals()
    rows = [r for r in list_predictions(ticker) if r.get("actual_direction")]
    by_model: dict[str, list[tuple[float, int]]] = {}
    for row in rows:
        key = row["model_name"]
        pair = _onehot_correct(row["predicted_direction"], row["actual_direction"], row["predicted_confidence"])
        by_model.setdefault(key, []).append(pair)

    feature_rows = [
        r for r in build_feature_rows(ticker, include_next=False, normalize=False)
        if r.get("target")
    ]
    maintained = _metrics(
        [(1.0, 1 if p == t else 0) for p, t in zip(always_maintained(feature_rows), [r["target"] for r in feature_rows])],
        "baseline_maintained",
    )
    mom = _metrics(
        [(1.0, 1 if p == t else 0) for p, t in zip(momentum(feature_rows), [r["target"] for r in feature_rows])],
        "baseline_momentum",
    )

    models = [_metrics(pairs, name) for name, pairs in sorted(by_model.items())]
    return {
        "models": models,
        "baselines": [maintained, mom],
        "n_graded": len(rows),
    }


def print_prediction_scorecard(ticker: str | None = None) -> None:
    report = score_predictions(ticker)
    print("\nPrediction Scorecard (graded vs extracted guidance)")
    print(f"  Graded rows: {report['n_graded']}")
    for block in report["models"] + report["baselines"]:
        if block.get("n", 0) == 0:
            continue
        print(
            f"  {block['name']:<22} n={block['n']:<4} acc={block['accuracy']:.3f} "
            f"brier={block['brier']:.4f} skill={block['skill_score']:.4f} ece={block['ece']:.4f}"
        )
    print()
