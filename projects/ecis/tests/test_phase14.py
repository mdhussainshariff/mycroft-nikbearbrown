"""Phase 14: Chroma metadata, quality, evaluation, drift, prediction watchdog."""

from datetime import date, timedelta

from ecis.db.init_db import get_connection, init_all, insert_default_weights
from ecis.embedding.hnsw import benchmark_recall, recall_at_k
from ecis.embedding.versioning import embedding_metadata, embedding_version
from ecis.quality.lineage import build_lineage, latest_lineage
from ecis.scoring.bootstrap import bootstrap_ci, paired_brier_skill
from ecis.scoring.drift import kl_divergence, psi
from ecis.scoring.power import extra_tickers_needed, n_for_ir
from ecis.scoring.significance import compare_model_brier, paired_permutation_diff, permutation_pvalue


def _init(tmp_path, monkeypatch):
    from ecis.config.settings import settings

    monkeypatch.setattr(settings, "db_dir", tmp_path)
    monkeypatch.setattr(settings, "fmp_api_key", "")
    init_all()
    insert_default_weights()


def _insert_signal(ticker, day, direction="raised", conf=0.8, model="llama3.1:8b"):
    conn = get_connection("signals")
    conn.execute(
        """INSERT INTO signals
           (ticker, direction, confidence_raw, source_method, supporting_quote,
            section_label, transcript_date, chunk_index, char_start, char_end,
            llm_model)
           VALUES (?, ?, ?, 'triangulated', 'guidance quote',
                   'prepared_remarks', ?, 0, 0, 40, ?)""",
        (ticker, direction, conf, day, model),
    )
    conn.commit()
    sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return sid


def _insert_outcome(signal_id, correct=1, excess=0.02, day=None):
    conn = get_connection("outcomes")
    conn.execute(
        """INSERT INTO outcomes
           (signal_id, horizon_days, excess_return, correct, transcript_date)
           VALUES (?, 90, ?, ?, ?)""",
        (signal_id, excess, correct, day or "2024-01-15"),
    )
    conn.commit()
    conn.close()


class TestEmbeddingVersion:
    def test_hash_stable_and_changes_with_model(self):
        a = embedding_version("sentence-transformers/all-MiniLM-L6-v2", 384)
        b = embedding_version("sentence-transformers/all-MiniLM-L6-v2", 384)
        c = embedding_version("other-model", 384)
        assert a == b
        assert a != c
        meta = embedding_metadata()
        assert "embedding_model" in meta
        assert "embedding_version" in meta


class TestHnswRecall:
    def test_recall_at_k(self):
        assert recall_at_k(["a", "b", "c"], {"a", "x"}, 2) == 0.5
        ranked = [(["a", "b"], {"a"}), (["x", "y"], {"z"})]
        out = benchmark_recall(ranked, ks=(1, 2))
        assert out["recall@1"] == 0.5


class TestExemplarDedup:
    def test_near_duplicates(self):
        from ecis.embedding.exemplar_cleanup import near_duplicate_ids

        ids = ["a", "b", "c"]
        embeds = [[1.0, 0.0], [0.999, 0.0], [0.0, 1.0]]
        drop = near_duplicate_ids(ids, embeds, threshold=0.95)
        assert "b" in drop
        assert "c" not in drop


class TestQuality:
    def test_profile_and_completeness(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        sid = _insert_signal("TICK", "2020-01-01")
        _insert_outcome(sid, correct=1, excess=0.05, day="2020-01-01")
        from ecis.quality.completeness import report_completeness
        from ecis.quality.profiler import profile_data

        profiles = profile_data("batch1")
        names = {p["field_name"] for p in profiles}
        assert "confidence_raw" in names
        assert "direction" in names

        reports = report_completeness("batch1")
        assert reports
        rec = reports[0]
        assert rec["missing_consensus"] == 1
        assert rec["ticker"] == "TICK"

    def test_lineage_roundtrip(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        blob = build_lineage(
            ticker="TICK",
            source_file="raw.txt",
            chunk_index=2,
            category="B",
            keyword={"matched": True},
            finbert={"direction": "raised"},
            llm={"direction": "raised", "model": "llama"},
            conflict=None,
            weights={"llm": 0.5},
            dedup="keep",
        )
        conn = get_connection("signals")
        conn.execute(
            """INSERT INTO signals
               (ticker, direction, confidence_raw, source_method, supporting_quote,
                section_label, transcript_date, chunk_index, char_start, char_end,
                lineage)
               VALUES ('TICK', 'raised', 0.7, 'triangulated', 'q',
                       'prepared_remarks', '2024-01-01', 2, 0, 10, ?)""",
            (blob,),
        )
        sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        parsed = latest_lineage(sid)
        assert parsed["raw_file"] == "raw.txt"
        assert parsed["escalation_category"] == "B"


class TestStats:
    def test_bootstrap_ci_covers_mean(self):
        ci = bootstrap_ci([1.0, 2.0, 3.0, 4.0], n_boot=200)
        assert ci["lo"] <= ci["estimate"] <= ci["hi"]

    def test_paired_brier(self):
        probs = [0.9, 0.8, 0.7, 0.2, 0.1]
        outs = [1, 1, 1, 0, 0]
        out = paired_brier_skill(probs, outs, n_boot=200)
        assert 0 <= out["brier"]["estimate"] <= 1
        assert out["brier"]["lo"] <= out["brier"]["estimate"] <= out["brier"]["hi"]

    def test_permutation_pvalue(self):
        assert permutation_pvalue(5, [1, 2, 3], "greater") == 1 / 4

    def test_model_compare(self):
        groups = {
            "llama": ([0.9, 0.8, 0.7], [1, 1, 1]),
            "mistral": ([0.2, 0.3, 0.4], [1, 1, 1]),
        }
        rows = compare_model_brier(groups, n_perm=200)
        assert rows
        assert rows[0]["p_value"] <= 1.0

    def test_paired_perm_identical_is_high_p(self):
        out = paired_permutation_diff([1, 2, 3], [1, 2, 3], n_perm=200)
        assert out["p_value"] > 0.2

    def test_power_ir(self):
        assert n_for_ir(0.5) >= 20
        extra = extra_tickers_needed(5)
        assert extra["extra_tickers"] >= 0


class TestDriftAndWatch:
    def test_psi_identical_near_zero(self):
        xs = [0.1, 0.2, 0.3, 0.4, 0.5] * 4
        assert psi(xs, xs) < 0.01
        assert kl_divergence(xs, xs) < 0.01

    def test_drift_and_decay(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.prediction.decay_watch import watch_decay
        from ecis.prediction.log import log_prediction
        from ecis.scoring.drift import check_drift

        for i in range(10):
            log_prediction(
                "TICK",
                f"2024-0{1 + (i // 9)}-{10 + i:02d}" if i < 9 else "2024-02-01",
                "raised",
                0.2 + i * 0.05,
                {},
                "logistic",
                "v1",
            )
        result = check_drift()
        assert result["status"] in {"ok", "alert"}
        watch = watch_decay()
        assert "ok" in watch
        assert watch["n_graded"] == 0


class TestQueryMonitor:
    def test_times_sql(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        _insert_signal("TICK", "2024-01-01")
        from ecis.db.query_monitor import time_sql

        rec = time_sql("signals_by_ticker", "SELECT ticker, COUNT(*) AS n FROM signals GROUP BY ticker")
        assert rec["n"] == 1
        assert rec["elapsed_ms"] >= 0


class TestPoolStatus:
    def test_disabled_without_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from ecis.db.pool import pool_status

        status = pool_status()
        assert status["enabled"] is False


class TestEvaluateEmpty:
    def test_empty_eval(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.scoring.evaluation import evaluate

        report = evaluate()
        assert report["n"] == 0
        assert report["model_comparisons"] == []
