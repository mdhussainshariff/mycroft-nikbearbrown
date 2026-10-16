"""Batch-level extraction progress so a crashed run resumes after the last completed file."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ecis.db.init_db import get_connection, log_agent_action

logger = logging.getLogger(__name__)

STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_IN_PROGRESS = "in_progress"
STATUS_SKIPPED = "skipped"


def _path_key(transcript_path: str) -> str:
    return str(Path(transcript_path).resolve()) if transcript_path else ""


def is_complete(ticker: str, transcript_path: str, llm_model: str) -> bool:
    """True when this ticker/file/model triple already finished successfully."""
    conn = get_connection("checkpoints")
    try:
        row = conn.execute(
            """SELECT status FROM extraction_runs
               WHERE ticker = ? AND transcript_path = ? AND llm_model = ?""",
            (ticker.upper(), _path_key(transcript_path), llm_model),
        ).fetchone()
    except Exception:
        conn.close()
        return False
    conn.close()
    return bool(row) and row["status"] in {STATUS_COMPLETE, STATUS_SKIPPED}


def mark_run(
    ticker: str,
    transcript_path: str,
    llm_model: str,
    status: str,
    *,
    node_id: str | None = None,
    error: str | None = None,
    signal_count: int | None = None,
) -> None:
    conn = get_connection("checkpoints")
    conn.execute(
        """INSERT INTO extraction_runs
           (ticker, transcript_path, llm_model, status, node_id, error, signal_count, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(ticker, transcript_path, llm_model) DO UPDATE SET
             status = excluded.status,
             node_id = COALESCE(excluded.node_id, extraction_runs.node_id),
             error = excluded.error,
             signal_count = COALESCE(excluded.signal_count, extraction_runs.signal_count),
             updated_at = datetime('now')""",
        (
            ticker.upper(),
            _path_key(transcript_path),
            llm_model,
            status,
            node_id,
            error,
            signal_count,
        ),
    )
    conn.commit()
    conn.close()


def record_node(ticker: str, transcript_path: str, llm_model: str, node_id: str, state: dict | None = None) -> None:
    """Append a node-level snapshot for streaming observability."""
    payload = ""
    if state:
        slim = {
            k: state.get(k)
            for k in (
                "ticker",
                "transcript_path",
                "llm_model",
                "errors",
                "category_a_indices",
                "category_b_indices",
                "category_c_indices",
                "category_d_indices",
            )
            if k in state
        }
        slim["n_chunks"] = len(state.get("chunks") or [])
        slim["n_signals"] = len(state.get("final_signals") or state.get("triangulated_signals") or [])
        try:
            payload = json.dumps(slim, default=str)
        except TypeError:
            payload = json.dumps({"node_id": node_id})
    conn = get_connection("checkpoints")
    conn.execute(
        """INSERT INTO checkpoints (graph_id, node_id, state_json)
           VALUES (?, ?, ?)""",
        (f"{ticker.upper()}|{_path_key(transcript_path)}|{llm_model}", node_id, payload or "{}"),
    )
    conn.commit()
    conn.close()
    mark_run(ticker, transcript_path, llm_model, STATUS_IN_PROGRESS, node_id=node_id)


def last_node(ticker: str, transcript_path: str, llm_model: str) -> str | None:
    conn = get_connection("checkpoints")
    try:
        row = conn.execute(
            """SELECT node_id FROM extraction_runs
               WHERE ticker = ? AND transcript_path = ? AND llm_model = ?""",
            (ticker.upper(), _path_key(transcript_path), llm_model),
        ).fetchone()
    except Exception:
        conn.close()
        return None
    conn.close()
    return row["node_id"] if row else None


def log_resume_skip(ticker: str, transcript_path: str, llm_model: str) -> None:
    log_agent_action(
        "pipeline_checkpoint",
        f"{ticker} {Path(transcript_path).name} ({llm_model})",
        "skip_completed",
        "already extracted",
    )
    logger.info("Skipping completed extraction %s %s (%s)", ticker, Path(transcript_path).name, llm_model)
