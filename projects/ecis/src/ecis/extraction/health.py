"""Per-reader health after an extraction batch."""

from __future__ import annotations

from typing import Any

from ecis.db.init_db import get_connection, log_agent_action


def record_reader_health(batch_id: str = "latest") -> list[dict[str, Any]]:
    conn_s = get_connection("signals")
    rows = [dict(r) for r in conn_s.execute(
        """SELECT source_method, confidence_raw, retry_count, verification_status
           FROM signals"""
    ).fetchall()]
    conn_s.close()

    conn_a = get_connection("agents")
    try:
        rejects = conn_a.execute("SELECT COUNT(*) AS n FROM chunk_rejections").fetchone()["n"]
    except Exception:
        rejects = 0

    by: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by.setdefault(row["source_method"], []).append(row)

    reports = []
    for reader, items in by.items():
        n = len(items)
        abstain = sum(1 for r in items if (r.get("verification_status") == "rejected"))
        retries = [float(r.get("retry_count") or 0) for r in items]
        confs = [float(r.get("confidence_raw") or 0) for r in items]
        fail = rejects / max(n + rejects, 1)
        success = 1.0 - fail
        abstention = abstain / n if n else 0.0
        alert = None
        if fail > 0.20:
            alert = f"{reader} failure rate {fail:.0%} above 20%"
        if abstention > 0.35:
            alert = f"{reader} abstention rate {abstention:.0%} spiked"
        rec = {
            "reader_name": reader,
            "batch_id": batch_id,
            "success_rate": round(success, 4),
            "failure_rate": round(fail, 4),
            "abstention_rate": round(abstention, 4),
            "avg_confidence": round(sum(confs) / n, 4) if n else 0.0,
            "avg_retries": round(sum(retries) / n, 4) if n else 0.0,
            "n_chunks": n,
            "alert": alert,
        }
        conn_a.execute(
            """INSERT INTO reader_health
               (reader_name, batch_id, success_rate, failure_rate, abstention_rate,
                avg_confidence, avg_retries, n_chunks, alert)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec["reader_name"], rec["batch_id"], rec["success_rate"], rec["failure_rate"],
                rec["abstention_rate"], rec["avg_confidence"], rec["avg_retries"],
                rec["n_chunks"], rec["alert"],
            ),
        )
        if alert:
            log_agent_action("reader_health", alert, "alert", reader)
        reports.append(rec)
    conn_a.commit()
    conn_a.close()
    return reports


def latest_alerts() -> list[dict[str, Any]]:
    conn = get_connection("agents")
    try:
        rows = conn.execute(
            """SELECT reader_name, alert, created_at FROM reader_health
               WHERE alert IS NOT NULL ORDER BY created_at DESC LIMIT 20"""
        ).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()
    return [dict(r) for r in rows]
