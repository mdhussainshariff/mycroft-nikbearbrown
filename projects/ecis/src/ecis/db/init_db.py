"""Initialise the four SQLite databases used by ECIS."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ecis.config.settings import settings

_SIGNALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT    NOT NULL,
    direction        TEXT    NOT NULL CHECK (direction IN ('raised','lowered','maintained')),
    confidence_raw   REAL    NOT NULL CHECK (confidence_raw BETWEEN 0 AND 1),
    confidence_calibrated REAL CHECK (confidence_calibrated BETWEEN 0 AND 1),
    source_method    TEXT    NOT NULL,
    supporting_quote TEXT    NOT NULL,
    section_label    TEXT    NOT NULL,
    speaker          TEXT    DEFAULT '',
    speaker_role     TEXT,
    speaker_weight   REAL,
    chunk_quality    REAL,
    trend            TEXT,
    transcript_date  TEXT    NOT NULL,
    chunk_index      INTEGER NOT NULL,
    char_start       INTEGER NOT NULL,
    char_end         INTEGER NOT NULL,
    reasoning_trace  TEXT,
    ner_entities     TEXT,          -- JSON-encoded dict
    self_consistency_votes TEXT,    -- JSON-encoded list
    verification_status TEXT,
    llm_model        TEXT,
    content_hash     TEXT,
    retry_count      INTEGER NOT NULL DEFAULT 0,
    provenance       TEXT,
    raw_llm_output   TEXT,
    low_confidence   INTEGER NOT NULL DEFAULT 0,
    decay_profile    TEXT,
    keyword_density  REAL,
    negation_flag    INTEGER NOT NULL DEFAULT 0,
    surprise_score   REAL,
    flesch_kincaid   REAL,
    gunning_fog      REAL,
    hedging_index    REAL,
    fls_density      REAL,
    tone_shift       REAL,
    lineage          TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_date   ON signals(transcript_date);
CREATE INDEX IF NOT EXISTS idx_signals_hash ON signals(ticker, transcript_date, content_hash);
CREATE INDEX IF NOT EXISTS idx_signals_ticker_date ON signals(ticker, transcript_date);
CREATE INDEX IF NOT EXISTS idx_signals_direction_conf ON signals(direction, confidence_calibrated);
CREATE INDEX IF NOT EXISTS idx_signals_model_source ON signals(llm_model, source_method);
"""

_OUTCOMES_SCHEMA = """
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id        INTEGER NOT NULL,
    horizon_days     INTEGER NOT NULL CHECK (horizon_days IN (30, 90, 180)),
    stock_price_t0   REAL,
    stock_price_t1   REAL,
    benchmark_price_t0 REAL,
    benchmark_price_t1 REAL,
    stock_return     REAL,
    benchmark_return REAL,
    excess_return    REAL,
    correct          INTEGER,
    transcript_date  TEXT,
    split_adjusted   INTEGER NOT NULL DEFAULT 0,
    sector_etf       TEXT,
    sector_excess_return REAL,
    reaction_magnitude REAL,
    drift_5d         REAL,
    drift_10d        REAL,
    ret_same_day     REAL,
    ret_1_3d         REAL,
    ret_1_2w         REAL,
    volume_ratio     REAL,
    resolved_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(signal_id, horizon_days, transcript_date)
);

CREATE INDEX IF NOT EXISTS idx_outcomes_signal ON outcomes(signal_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_ticker_horizon ON outcomes(transcript_date, horizon_days);
"""

_AGENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_actions (
    action_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name       TEXT    NOT NULL,
    observation      TEXT    NOT NULL,
    action_taken     TEXT    NOT NULL,
    result           TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_actions_agent ON agent_actions(agent_name);

CREATE TABLE IF NOT EXISTS reader_weights (
    reader_name      TEXT    PRIMARY KEY,
    weight           REAL    NOT NULL CHECK (weight BETWEEN 0 AND 1),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS escalation_thresholds (
    param_name       TEXT    PRIMARY KEY,
    value            REAL    NOT NULL,
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vindication_records (
    record_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT    NOT NULL,
    chunk_index      INTEGER NOT NULL,
    conflict_type    TEXT    NOT NULL,
    vindicated_reader TEXT   NOT NULL,
    defeated_reader  TEXT    NOT NULL,
    reasoning        TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CHECKPOINTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_id         TEXT    NOT NULL,
    node_id          TEXT    NOT NULL,
    state_json       TEXT    NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_graph ON checkpoints(graph_id);

CREATE TABLE IF NOT EXISTS extraction_runs (
    run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT    NOT NULL,
    transcript_path  TEXT    NOT NULL,
    llm_model        TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'in_progress',
    node_id          TEXT,
    error            TEXT,
    signal_count     INTEGER,
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, transcript_path, llm_model)
);

CREATE INDEX IF NOT EXISTS idx_extraction_runs_status ON extraction_runs(status);
"""

_FILE_METADATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS file_metadata (
    file_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT    NOT NULL,
    filing_date      TEXT    NOT NULL,
    source           TEXT    NOT NULL CHECK (source IN ('edgar','fmp')),
    file_path        TEXT    NOT NULL UNIQUE,
    period_of_report TEXT,
    downloaded_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_file_meta_ticker ON file_metadata(ticker);
"""

_TICKERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
    ticker                    TEXT PRIMARY KEY,
    company_name              TEXT NOT NULL DEFAULT '',
    sector                    TEXT NOT NULL DEFAULT 'AI',
    fiscal_calendar           TEXT NOT NULL DEFAULT 'calendar',
    transcript_source         TEXT NOT NULL DEFAULT 'both',
    total_transcripts         INTEGER NOT NULL DEFAULT 0,
    last_ingestion_date       TEXT,
    extraction_status         TEXT NOT NULL DEFAULT 'pending',
    outcome_resolution_status TEXT NOT NULL DEFAULT 'pending',
    updated_at                TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CHUNK_CLASSIFICATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk_classifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT    NOT NULL,
    transcript_date     TEXT,
    chunk_index         INTEGER NOT NULL,
    category            TEXT    NOT NULL,
    keyword_matched     INTEGER NOT NULL DEFAULT 0,
    keyword_confidence  REAL    NOT NULL DEFAULT 0,
    finbert_confidence  REAL    NOT NULL DEFAULT 0,
    finbert_direction   TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chunk_class_ticker ON chunk_classifications(ticker);
CREATE INDEX IF NOT EXISTS idx_chunk_class_cat ON chunk_classifications(category);
"""

_PENDING_APPROVALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_approvals (
    approval_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name     TEXT    NOT NULL,
    action_type    TEXT    NOT NULL,
    proposal_json  TEXT    NOT NULL,
    evidence_json  TEXT,
    status         TEXT    NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','approved','rejected')),
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at    TEXT,
    resolution_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_approvals_status ON pending_approvals(status);
"""

_TRANSCRIPT_HASHES_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_hashes (
    hash_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT    NOT NULL,
    transcript_hash  TEXT    NOT NULL,
    file_path        TEXT    NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, transcript_hash)
);
"""

_COMPANY_OFFICERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS company_officers (
    officer_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT    NOT NULL,
    name_key      TEXT    NOT NULL,
    display_name  TEXT    NOT NULL DEFAULT '',
    role          TEXT    NOT NULL,
    source        TEXT    NOT NULL DEFAULT 'transcript',
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, name_key)
);

CREATE INDEX IF NOT EXISTS idx_officers_ticker ON company_officers(ticker);
"""

_PREDICTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker               TEXT    NOT NULL,
    as_of_date           TEXT    NOT NULL,
    predicted_direction  TEXT    NOT NULL CHECK (predicted_direction IN ('raised','lowered','maintained')),
    predicted_confidence REAL    NOT NULL CHECK (predicted_confidence BETWEEN 0 AND 1),
    features_json        TEXT,
    model_name           TEXT    NOT NULL,
    model_version        TEXT    NOT NULL DEFAULT 'v1',
    actual_direction     TEXT,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, as_of_date, model_name, model_version)
);

CREATE INDEX IF NOT EXISTS idx_predictions_ticker ON predictions(ticker);
"""

_MONITORING_SCHEMA = """
CREATE TABLE IF NOT EXISTS reader_health (
    health_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    reader_name      TEXT    NOT NULL,
    batch_id         TEXT,
    success_rate     REAL,
    failure_rate     REAL,
    abstention_rate  REAL,
    avg_confidence   REAL,
    avg_retries      REAL,
    n_chunks         INTEGER,
    alert            TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS extraction_latency (
    latency_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT,
    chunk_index      INTEGER,
    reader_name      TEXT    NOT NULL,
    elapsed_ms       REAL    NOT NULL,
    retry_ms         REAL    NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS correlations (
    corr_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_a         TEXT    NOT NULL,
    ticker_b         TEXT    NOT NULL,
    lag_quarters     INTEGER NOT NULL DEFAULT 0,
    coefficient      REAL    NOT NULL,
    n_overlap        INTEGER NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker_a, ticker_b, lag_quarters)
);

CREATE TABLE IF NOT EXISTS market_prices (
    price_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT    NOT NULL,
    price_date       TEXT    NOT NULL,
    close            REAL    NOT NULL,
    volume           REAL,
    UNIQUE(ticker, price_date)
);

CREATE INDEX IF NOT EXISTS idx_market_prices_ticker_date ON market_prices(ticker, price_date);

CREATE TABLE IF NOT EXISTS data_profiles (
    profile_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      TEXT,
    field_name    TEXT    NOT NULL,
    field_kind    TEXT    NOT NULL,
    n             INTEGER,
    missing       INTEGER,
    mean          REAL,
    median_val    REAL,
    stdev         REAL,
    p05           REAL,
    p95           REAL,
    iqr_outliers  INTEGER,
    extra_json    TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS query_stats (
    stat_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    query_name   TEXT    NOT NULL,
    elapsed_ms   REAL    NOT NULL,
    used_index   INTEGER,
    note         TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS drift_alerts (
    alert_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    feature      TEXT    NOT NULL,
    metric       TEXT    NOT NULL,
    value        REAL    NOT NULL,
    window_a     TEXT,
    window_b     TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS completeness_reports (
    report_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT    NOT NULL,
    missing_consensus INTEGER NOT NULL DEFAULT 0,
    missing_prices     INTEGER NOT NULL DEFAULT 0,
    missing_chroma     INTEGER NOT NULL DEFAULT 0,
    missing_outcomes   INTEGER NOT NULL DEFAULT 0,
    notes        TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CHUNK_REJECTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk_rejections (
    rejection_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT,
    transcript_date  TEXT,
    chunk_index      INTEGER,
    reason           TEXT NOT NULL,
    token_count      INTEGER,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

DB_MAP: dict[str, str] = {
    "signals": _SIGNALS_SCHEMA,
    "outcomes": _OUTCOMES_SCHEMA,
    "agents": (
        _AGENTS_SCHEMA
        + _FILE_METADATA_SCHEMA
        + _TICKERS_SCHEMA
        + _CHUNK_CLASSIFICATIONS_SCHEMA
        + _PENDING_APPROVALS_SCHEMA
        + _CHUNK_REJECTIONS_SCHEMA
        + _TRANSCRIPT_HASHES_SCHEMA
        + _COMPANY_OFFICERS_SCHEMA
        + _PREDICTIONS_SCHEMA
        + _MONITORING_SCHEMA
    ),
    "checkpoints": _CHECKPOINTS_SCHEMA,
}


def _db_path(name: str) -> Path:
    return settings.db_dir / f"{name}.db"


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def migrate_schema(conn: sqlite3.Connection, name: str) -> None:
    """Apply additive migrations to an existing database."""
    if name == "signals":
        try:
            _ensure_column(conn, "signals", "llm_model", "llm_model TEXT")
            _ensure_column(conn, "signals", "content_hash", "content_hash TEXT")
            _ensure_column(conn, "signals", "retry_count", "retry_count INTEGER NOT NULL DEFAULT 0")
            _ensure_column(conn, "signals", "provenance", "provenance TEXT")
            _ensure_column(conn, "signals", "raw_llm_output", "raw_llm_output TEXT")
            _ensure_column(conn, "signals", "low_confidence", "low_confidence INTEGER NOT NULL DEFAULT 0")
            _ensure_column(conn, "signals", "speaker_role", "speaker_role TEXT")
            _ensure_column(conn, "signals", "speaker_weight", "speaker_weight REAL")
            _ensure_column(conn, "signals", "chunk_quality", "chunk_quality REAL")
            _ensure_column(conn, "signals", "trend", "trend TEXT")
            _ensure_column(conn, "signals", "decay_profile", "decay_profile TEXT")
            _ensure_column(conn, "signals", "keyword_density", "keyword_density REAL")
            _ensure_column(conn, "signals", "negation_flag", "negation_flag INTEGER NOT NULL DEFAULT 0")
            _ensure_column(conn, "signals", "surprise_score", "surprise_score REAL")
            _ensure_column(conn, "signals", "flesch_kincaid", "flesch_kincaid REAL")
            _ensure_column(conn, "signals", "gunning_fog", "gunning_fog REAL")
            _ensure_column(conn, "signals", "hedging_index", "hedging_index REAL")
            _ensure_column(conn, "signals", "fls_density", "fls_density REAL")
            _ensure_column(conn, "signals", "tone_shift", "tone_shift REAL")
            _ensure_column(conn, "signals", "lineage", "lineage TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    elif name == "outcomes":
        try:
            _ensure_column(conn, "outcomes", "transcript_date", "transcript_date TEXT")
            _ensure_column(conn, "outcomes", "split_adjusted", "split_adjusted INTEGER NOT NULL DEFAULT 0")
            _ensure_column(conn, "outcomes", "sector_etf", "sector_etf TEXT")
            _ensure_column(conn, "outcomes", "sector_excess_return", "sector_excess_return REAL")
            _ensure_column(conn, "outcomes", "reaction_magnitude", "reaction_magnitude REAL")
            _ensure_column(conn, "outcomes", "drift_5d", "drift_5d REAL")
            _ensure_column(conn, "outcomes", "drift_10d", "drift_10d REAL")
            _ensure_column(conn, "outcomes", "ret_same_day", "ret_same_day REAL")
            _ensure_column(conn, "outcomes", "ret_1_3d", "ret_1_3d REAL")
            _ensure_column(conn, "outcomes", "ret_1_2w", "ret_1_2w REAL")
            _ensure_column(conn, "outcomes", "volume_ratio", "volume_ratio REAL")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    elif name == "agents":
        conn.executescript(_TICKERS_SCHEMA)
        conn.executescript(_CHUNK_CLASSIFICATIONS_SCHEMA)
        conn.executescript(_PENDING_APPROVALS_SCHEMA)
        conn.executescript(_CHUNK_REJECTIONS_SCHEMA)
        conn.executescript(_TRANSCRIPT_HASHES_SCHEMA)
        conn.executescript(_COMPANY_OFFICERS_SCHEMA)
        conn.executescript(_PREDICTIONS_SCHEMA)
        conn.executescript(_MONITORING_SCHEMA)
        try:
            _ensure_column(conn, "file_metadata", "period_of_report", "period_of_report TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    elif name == "checkpoints":
        conn.executescript(_CHECKPOINTS_SCHEMA)
        conn.commit()


_MIGRATED_PATHS: set[str] = set()


def init_database(name: str) -> None:
    path = _db_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(DB_MAP[name])
    migrate_schema(conn, name)
    conn.close()


def init_all() -> None:
    settings.ensure_dirs()
    _MIGRATED_PATHS.clear()
    for name in DB_MAP:
        init_database(name)
        print(f"  ✓ {_db_path(name)}")


def get_connection(name: str) -> sqlite3.Connection:
    path = _db_path(name)
    if not path.exists():
        init_database(name)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    key = str(path)
    if key not in _MIGRATED_PATHS:
        migrate_schema(conn, name)
        _MIGRATED_PATHS.add(key)
    return conn


def log_agent_action(
    agent_name: str,
    observation: str,
    action_taken: str,
    result: str | None = None,
) -> None:
    """Append a row to the agent audit log."""
    conn = get_connection("agents")
    conn.execute(
        """INSERT INTO agent_actions (agent_name, observation, action_taken, result)
           VALUES (?, ?, ?, ?)""",
        (agent_name, observation, action_taken, result),
    )
    conn.commit()
    conn.close()


def insert_default_weights() -> None:
    conn = get_connection("agents")
    defaults = [
        ("keyword", settings.weight_keyword),
        ("finbert", settings.weight_finbert),
        ("llm", settings.weight_llm),
        ("llm_llama", settings.weight_llm_llama),
        ("llm_mistral", settings.weight_llm_mistral),
        ("llm_qwen", settings.weight_llm_qwen),
        ("llm_finetuned", settings.weight_llm_finetuned),
        ("agreement", settings.weight_agreement),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO reader_weights (reader_name, weight) VALUES (?, ?)",
        defaults,
    )
    threshold_defaults = [
        ("finbert_confidence_min", 0.6),
        ("keyword_confidence_min", 0.5),
        ("escalation_agreement_threshold", 0.7),
        ("use_finetuned_adapter", 1.0),
        ("finetuned_skill_delta_min", 0.05),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO escalation_thresholds (param_name, value) VALUES (?, ?)",
        threshold_defaults,
    )
    conn.commit()
    conn.close()


def get_threshold(param_name: str, default: float) -> float:
    conn = get_connection("agents")
    try:
        row = conn.execute(
            "SELECT value FROM escalation_thresholds WHERE param_name = ?",
            (param_name,),
        ).fetchone()
    except Exception:
        conn.close()
        return default
    conn.close()
    return float(row["value"]) if row else default


def set_threshold(param_name: str, value: float) -> None:
    conn = get_connection("agents")
    conn.execute(
        """INSERT INTO escalation_thresholds (param_name, value, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(param_name) DO UPDATE SET
             value = excluded.value, updated_at = datetime('now')""",
        (param_name, value),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    print("Initialising ECIS databases…")
    init_all()
    insert_default_weights()
    print("Done.")
