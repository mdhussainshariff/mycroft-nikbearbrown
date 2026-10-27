"""Embedding model identifier and version hash for Chroma metadata."""

from __future__ import annotations

import hashlib

from ecis.config.settings import settings

TRANSCRIPT_COLLECTION = "ecis_transcripts"
EXEMPLAR_COLLECTION = "ecis_exemplars"


def embedding_version(model_name: str | None = None, dim: int | None = None) -> str:
    name = model_name or settings.embedding_model_name
    size = dim if dim is not None else settings.embedding_dim
    raw = f"{name}|{size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def embedding_metadata() -> dict[str, str]:
    return {
        "embedding_model": settings.embedding_model_name,
        "embedding_version": embedding_version(),
    }


def collection_metadata() -> dict:
    return {
        "hnsw:space": "cosine",
        "hnsw:construction_ef": settings.hnsw_ef_construction,
        "hnsw:M": settings.hnsw_m,
        "embedding_model": settings.embedding_model_name,
        "embedding_version": embedding_version(),
        "collection_strategy": "unified_metadata_filter",
    }


def archive_collection_name(base: str) -> str:
    return f"{base}_{embedding_version()}"


def archive_on_upgrade(base: str = TRANSCRIPT_COLLECTION) -> str:
    """Rename the live collection so a new MiniLM checkpoint can be written beside it."""
    from ecis.embedding.embedder import _get_chroma_client

    client = _get_chroma_client()
    archived = archive_collection_name(base)
    try:
        existing = {c.name for c in client.list_collections()}
        if base in existing and archived not in existing:
            client.get_collection(base).modify(name=archived)
    except Exception:
        pass
    return archived
