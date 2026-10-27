"""Swappable tabular classifiers: logistic regression (primary) and XGBoost/GBT."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import numpy as np

from ecis.prediction.features import FEATURE_NAMES, build_feature_rows
from ecis.prediction.log import log_prediction

logger = logging.getLogger(__name__)

MODEL_VERSION = "v1"
LABELS = ["lowered", "maintained", "raised"]


def _temporal_split(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labelled = [r for r in rows if r.get("target")]
    if len(labelled) < 4:
        return labelled, []
    holdout_day = max(r["target_date"] for r in labelled if r.get("target_date"))
    train = [r for r in labelled if r["target_date"] != holdout_day]
    test = [r for r in labelled if r["target_date"] == holdout_day]
    if not train:
        return labelled[:-1], labelled[-1:]
    return train, test


def _fit_logistic(X: np.ndarray, y: list[str]):
    from sklearn.linear_model import LogisticRegression

    clf = LogisticRegression(max_iter=400, class_weight="balanced")
    clf.fit(X, y)
    return clf


def _fit_tree(X: np.ndarray, y: list[str]):
    from sklearn.preprocessing import LabelEncoder

    enc = LabelEncoder()
    y_num = enc.fit_transform(y)
    try:
        from xgboost import XGBClassifier

        inner = XGBClassifier(
            n_estimators=80,
            max_depth=3,
            learning_rate=0.1,
            eval_metric="mlogloss",
            verbosity=0,
        )
        inner.fit(X, y_num)
        return _LabelWrapped(inner, enc), "xgboost"
    except Exception:
        from sklearn.ensemble import GradientBoostingClassifier

        inner = GradientBoostingClassifier(n_estimators=80, max_depth=2)
        inner.fit(X, y)
        return inner, "gbt"


class _LabelWrapped:
    def __init__(self, clf, enc):
        self.clf = clf
        self.enc = enc
        self.classes_ = enc.classes_
        self.feature_importances_ = getattr(clf, "feature_importances_", None)

    def predict_proba(self, X):
        return self.clf.predict_proba(X)


def _proba(clf, X: np.ndarray) -> list[dict[str, float]]:
    classes = list(getattr(clf, "classes_", LABELS))
    raw = clf.predict_proba(X)
    out = []
    for row in raw:
        dist = {c: float(p) for c, p in zip(classes, row)}
        for label in LABELS:
            dist.setdefault(label, 0.0)
        out.append(dist)
    return out


def _drivers(clf, vector: list[float], name: str) -> list[tuple[str, float]]:
    if hasattr(clf, "coef_"):
        coef = np.mean(np.abs(clf.coef_), axis=0)
        scored = list(zip(FEATURE_NAMES, (coef * np.abs(vector)).tolist()))
        return sorted(scored, key=lambda p: p[1], reverse=True)[:5]
    if hasattr(clf, "feature_importances_"):
        scored = list(zip(FEATURE_NAMES, clf.feature_importances_.tolist()))
        return sorted(scored, key=lambda p: p[1], reverse=True)[:5]
    return []


def train_and_predict(
    ticker: str | None = None,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Train on all but the latest quarter; predict that quarter and any next-call rows."""
    rows = build_feature_rows(ticker, include_next=True, normalize=True)
    labelled = [r for r in rows if r.get("target")]
    train, test = _temporal_split(labelled)
    forecast = [r for r in rows if r.get("target") is None]

    if len(train) < 3:
        return {
            "trained": False,
            "reason": "need at least 3 labelled quarters after the first",
            "n_train": len(train),
            "predictions": [],
        }

    X_train = np.array([r["vector"] for r in train], dtype=float)
    y_train = [r["target"] for r in train]
    logistic = _fit_logistic(X_train, y_train)
    tree, tree_name = _fit_tree(X_train, y_train)

    scored: list[dict[str, Any]] = []
    to_score = test + forecast
    if not to_score:
        to_score = labelled[-1:]

    for model, model_name in ((logistic, "logistic"), (tree, tree_name)):
        X = np.array([r["vector"] for r in to_score], dtype=float)
        dists = _proba(model, X)
        for row, dist in zip(to_score, dists):
            winner = max(dist, key=dist.get)
            record = {
                "ticker": row["ticker"],
                "as_of_date": row["as_of_date"],
                "predicted_direction": winner,
                "predicted_confidence": round(dist[winner], 4),
                "distribution": dist,
                "features": row["features"],
                "drivers": _drivers(model, row["vector"], model_name),
                "model_name": model_name,
                "model_version": MODEL_VERSION,
                "actual_direction": row.get("target"),
            }
            scored.append(record)
            if persist:
                log_prediction(
                    row["ticker"],
                    row["as_of_date"],
                    winner,
                    dist[winner],
                    row["features"],
                    model_name,
                    MODEL_VERSION,
                )

    return {
        "trained": True,
        "n_train": len(train),
        "n_test": len(test),
        "class_counts": dict(Counter(y_train)),
        "predictions": scored,
    }
