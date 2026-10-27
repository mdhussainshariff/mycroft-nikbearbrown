"""Phases 11–13: prediction, linguistics, surprise, correlation, views."""

from ecis.db.init_db import get_connection, init_all, insert_default_weights
from ecis.extraction.linguistics import flesch_kincaid, hedging_index, ks_statistic, score_text
from ecis.prediction.baselines import always_maintained, momentum
from ecis.prediction.consensus import consensus_direction
from ecis.prediction.features import encode_direction
from ecis.prediction.surprise import surprise_value


def _init(tmp_path, monkeypatch):
    from ecis.config.settings import settings

    monkeypatch.setattr(settings, "db_dir", tmp_path)
    init_all()
    insert_default_weights()


def _insert_signal(ticker, day, direction, conf=0.8, speaker_role="cfo"):
    conn = get_connection("signals")
    conn.execute(
        """INSERT INTO signals
           (ticker, direction, confidence_raw, source_method, supporting_quote,
            section_label, transcript_date, chunk_index, char_start, char_end,
            speaker_role)
           VALUES (?, ?, ?, 'triangulated', 'We are raising full year guidance.',
                   'prepared_remarks', ?, 0, 0, 40, ?)""",
        (ticker, direction, conf, day, speaker_role),
    )
    conn.commit()
    conn.close()


class TestDirectionEncoding:
    def test_codes(self):
        assert encode_direction("raised") == 1.0
        assert encode_direction("lowered") == -1.0
        assert encode_direction("maintained") == 0.0


class TestLinguistics:
    def test_hedging_and_readability(self):
        text = "We believe revenue may grow. We expect guidance is higher next quarter."
        scores = score_text(text)
        assert 0 <= scores["hedging_index"] <= 1
        assert scores["fls_density"] > 0
        assert flesch_kincaid(text) != 0.0
        assert hedging_index("we will raise guidance") < hedging_index("we believe we may raise")

    def test_ks_identical_is_zero(self):
        assert ks_statistic([0.2, 0.4], [0.2, 0.4]) == 0.0
        assert ks_statistic([0.1], [0.9]) > 0


class TestSurprise:
    def test_values(self):
        assert surprise_value("raised", "raised") == 0.0
        assert surprise_value("raised", "lowered") == 1.0
        assert surprise_value("raised", "maintained") == 0.5
        assert consensus_direction(0.2) == "raised"
        assert consensus_direction(-0.2) == "lowered"
        assert consensus_direction(0.0) == "maintained"


class TestBaselines:
    def test_maintained_and_momentum(self):
        rows = [
            {"features": {"prior_direction": 1.0}},
            {"features": {"prior_direction": -1.0}},
            {"features": {"prior_direction": 0.0}},
        ]
        assert always_maintained(rows) == ["maintained"] * 3
        assert momentum(rows) == ["raised", "lowered", "maintained"]


class TestPredictionLog:
    def test_log_and_fill(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.prediction.log import fill_actuals, list_predictions, log_prediction

        log_prediction("TICKER", "2024-01-15", "raised", 0.7, {"prior_direction": 1}, "logistic", "v1")
        _insert_signal("TICKER", "2024-04-15", "raised")
        assert fill_actuals() == 1
        rows = list_predictions("TICKER")
        assert rows[0]["actual_direction"] == "raised"
        assert rows[0]["predicted_direction"] == "raised"


class TestCorrelation:
    def test_pearson_and_update(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        for i, day in enumerate(("2024-01-15", "2024-04-15", "2024-07-15")):
            _insert_signal("AAA", day, "raised" if i < 2 else "lowered")
            _insert_signal("BBB", day, "raised" if i < 2 else "lowered")
        from ecis.extraction.correlation import list_correlations, update_correlations

        result = update_correlations()
        assert result["pairs"] >= 1
        rows = list_correlations(0)
        assert rows
        assert abs(rows[0]["coefficient"]) > 0.5


class TestLinguisticsLink:
    def test_writes_columns(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        _insert_signal("TICKER", "2024-01-15", "maintained")
        from ecis.extraction.linguistics import link_linguistics

        assert link_linguistics("TICKER")["labelled"] == 1
        conn = get_connection("signals")
        row = conn.execute("SELECT hedging_index, fls_density FROM signals").fetchone()
        conn.close()
        assert row["fls_density"] is not None


class TestViewsAndHealth:
    def test_refresh_and_health(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        _insert_signal("TICKER", "2024-01-15", "raised")
        from ecis.db.views import refresh_views
        from ecis.extraction.health import record_reader_health

        counts = refresh_views()
        assert counts["readers"] >= 1
        reports = record_reader_health()
        assert reports
        assert reports[0]["n_chunks"] >= 1
