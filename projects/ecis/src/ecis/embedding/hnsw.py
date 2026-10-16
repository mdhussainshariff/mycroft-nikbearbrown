"""HNSW parameter notes and a small recall helper for retrieval tuning."""

from __future__ import annotations

from typing import Any


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids or k <= 0:
        return 0.0
    hit = sum(1 for i in retrieved_ids[:k] if i in relevant_ids)
    return hit / min(k, len(relevant_ids))


def benchmark_recall(
    ranked: list[tuple[list[str], set[str]]],
    ks: tuple[int, ...] = (5, 10),
) -> dict[str, float]:
    """ranked: list of (retrieved_id_order, relevant_id_set)."""
    out: dict[str, float] = {}
    for k in ks:
        scores = [recall_at_k(ids, rel, k) for ids, rel in ranked]
        out[f"recall@{k}"] = round(sum(scores) / len(scores), 4) if scores else 0.0
    return out


def recommended_params() -> dict[str, Any]:
    from ecis.config.settings import settings

    return {
        "M": settings.hnsw_m,
        "ef_construction": settings.hnsw_ef_construction,
        "ef_search": settings.hnsw_ef_search,
        "space": "cosine",
        "use_case": "few-shot and temporal retrieval on MiniLM financial chunks",
    }
