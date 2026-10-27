"""Company officer lookup: map name-only speakers to roles learned from titled attributions."""

from __future__ import annotations

import logging
import re

from ecis.db.init_db import get_connection

logger = logging.getLogger(__name__)

_TITLE_STRIP = re.compile(
    r"(?i)\s*[,–—-]\s*(?:ceo|cfo|coo|cto|ir|president|chairman|director|analyst|"
    r"operator|chief\s+\w+(?:\s+\w+)*|vice\s+president|svp|evp).*$"
)
_NON_NAME = re.compile(r"[^a-z\s'-]")


def name_key(speaker: str) -> str:
    """Canonical person name: titles stripped, lowercased, extra punctuation removed."""
    text = (speaker or "").strip()
    if not text:
        return ""
    without_title = _TITLE_STRIP.sub("", text).strip()
    cleaned = _NON_NAME.sub(" ", without_title.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def upsert_officer(ticker: str, speaker: str, role: str, source: str = "transcript") -> None:
    """Persist a titled speaker so later name-only mentions can reuse the role."""
    if role in {"unknown", "analyst", "operator", ""}:
        return
    key = name_key(speaker)
    if not key or len(key.split()) < 2:
        return
    ticker = ticker.upper().strip()
    if not ticker:
        return
    conn = get_connection("agents")
    conn.execute(
        """INSERT INTO company_officers (ticker, name_key, display_name, role, source, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(ticker, name_key) DO UPDATE SET
             role = excluded.role,
             display_name = excluded.display_name,
             source = excluded.source,
             updated_at = datetime('now')""",
        (ticker, key, speaker.strip(), role, source),
    )
    conn.commit()
    conn.close()


def lookup_role(ticker: str | None, speaker: str) -> str | None:
    """Return a stored role for a name-only attribution, or None."""
    if not ticker:
        return None
    key = name_key(speaker)
    if not key:
        return None
    conn = get_connection("agents")
    try:
        row = conn.execute(
            "SELECT role FROM company_officers WHERE ticker = ? AND name_key = ?",
            (ticker.upper(), key),
        ).fetchone()
    except Exception:
        conn.close()
        return None
    conn.close()
    return row["role"] if row else None


def ingest_from_speaker(ticker: str, speaker: str, role: str) -> None:
    """Record an officer when classification found a title on this utterance."""
    try:
        upsert_officer(ticker, speaker, role, source="transcript")
    except Exception as exc:
        logger.debug("Officer upsert failed for %s / %s: %s", ticker, speaker, exc)
