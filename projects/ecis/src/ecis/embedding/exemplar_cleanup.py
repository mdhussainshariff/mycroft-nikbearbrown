"""Deduplicate and rebalance the few-shot exemplar collection."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

NEAR_DUP = 0.95
DIRECTIONS = ("raised", "lowered", "maintained", "none")


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def near_duplicate_ids(
    ids: list[str],
    embeds: list[Any],
    threshold: float = NEAR_DUP,
) -> set[str]:
    drop: set[str] = set()
    for i in range(len(ids)):
        if ids[i] in drop:
            continue
        for j in range(i + 1, len(ids)):
            if ids[j] in drop:
                continue
            if _cosine(np.array(embeds[i]), np.array(embeds[j])) >= threshold:
                drop.add(ids[j])
    return drop


def cleanup_exemplars(max_per_direction: int = 40) -> dict[str, Any]:
    from ecis.embedding.exemplar_store import add_exemplar, get_exemplar_collection

    collection = get_exemplar_collection()
    try:
        data = collection.get(include=["embeddings", "metadatas", "documents"])
    except Exception as exc:
        logger.debug("Exemplar get failed: %s", exc)
        return {"removed": 0, "kept": 0, "rebalanced": False}

    ids = data.get("ids") or []
    embeds = data.get("embeddings") or []
    metas = data.get("metadatas") or []
    if not ids:
        return {"removed": 0, "kept": 0, "rebalanced": False}

    drop = near_duplicate_ids(ids, embeds)
    if drop:
        collection.delete(ids=list(drop))

    kept_idx = [i for i, eid in enumerate(ids) if eid not in drop]
    counts = Counter((metas[i] or {}).get("direction", "none") for i in kept_idx)
    for direction in DIRECTIONS:
        if counts.get(direction, 0) == 0:
            add_exemplar(
                exemplar_id=f"boundary_{direction}_auto",
                chunk_text=(
                    "We are not changing the outlook. Results were in line with "
                    "the previously communicated range; no revision at this time."
                    if direction in {"none", "maintained"}
                    else f"Synthetic {direction} guidance exemplar for class balance."
                ),
                direction=direction,
                confidence=0.55,
                supporting_quote="no revision at this time" if direction == "none" else direction,
                reasoning_trace="Adversarial maintained/none boundary exemplar.",
                signal_category="boundary",
                is_negative=(direction == "none"),
            )
            counts[direction] += 1

    _ = max_per_direction
    return {
        "removed": len(drop),
        "kept": len(ids) - len(drop),
        "by_direction": dict(counts),
        "rebalanced": True,
    }
