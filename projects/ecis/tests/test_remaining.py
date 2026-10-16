"""Tests for crash recovery, officer lookup, and fine-tuned watchdog reversion."""

from datetime import date
from pathlib import Path

from ecis.db.init_db import get_connection, get_threshold, init_all, insert_default_weights, set_threshold
from ecis.extraction.officer_lookup import lookup_role, name_key, upsert_officer
from ecis.extraction.speaker_roles import classify_speaker


def _init(tmp_path, monkeypatch):
    from ecis.config.settings import settings

    monkeypatch.setattr(settings, "db_dir", tmp_path)
    init_all()
    insert_default_weights()


class TestCrashRecovery:
    def test_mark_and_skip(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.db.crash_recovery import STATUS_COMPLETE, is_complete, mark_run

        path = str(tmp_path / "call.json")
        Path(path).write_text("x")
        assert is_complete("TICKER", path, "llama") is False
        mark_run("TICKER", path, "llama", STATUS_COMPLETE, node_id="logging", signal_count=3)
        assert is_complete("TICKER", path, "llama") is True
        assert is_complete("TICKER", path, "mistral") is False

    def test_failed_run_is_not_complete(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.db.crash_recovery import STATUS_FAILED, is_complete, mark_run

        path = str(tmp_path / "call.json")
        Path(path).write_text("x")
        mark_run("TICKER", path, "llama", STATUS_FAILED, error="boom")
        assert is_complete("TICKER", path, "llama") is False

    def test_node_checkpoint_row(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.db.crash_recovery import last_node, record_node

        path = str(tmp_path / "call.json")
        Path(path).write_text("x")
        record_node("TICKER", path, "llama", "chunking", {"chunks": [1, 2]})
        assert last_node("TICKER", path, "llama") == "chunking"
        conn = get_connection("checkpoints")
        row = conn.execute("SELECT node_id FROM checkpoints").fetchone()
        conn.close()
        assert row["node_id"] == "chunking"


class TestOfficerLookup:
    def test_name_key_strips_title(self):
        assert name_key("Jane Doe, Chief Financial Officer") == "jane doe"
        assert name_key("Jane Doe") == "jane doe"

    def test_titled_then_name_only(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        assert classify_speaker("Jane Doe") == "unknown"
        assert classify_speaker("Jane Doe, CFO", ticker="TICKER") == "cfo"
        assert lookup_role("TICKER", "Jane Doe") == "cfo"
        assert classify_speaker("Jane Doe", ticker="TICKER") == "cfo"
        assert classify_speaker("Jane Doe", ticker="OTHER") == "unknown"

    def test_upsert_skips_analysts(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        upsert_officer("TICKER", "Pat Lee, Analyst", "analyst")
        assert lookup_role("TICKER", "Pat Lee") is None


class TestFinetunedReversion:
    def test_negative_skill_reverts(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.extraction.finetuned_guard import finetuned_reversion_needed

        revert, details = finetuned_reversion_needed(-0.1)
        assert revert is True
        assert "negative" in details["reason"].lower()

    def test_revert_disables_adapter(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.config.settings import settings
        from ecis.extraction.finetuned_guard import apply_finetuned_gate, revert_finetuned_adapter

        revert_finetuned_adapter({"reason": "test"})
        assert get_threshold("use_finetuned_adapter", 1.0) == 0.0
        gated = apply_finetuned_gate("finetuned", [settings.llm_finetuned_model])
        assert gated == [settings.llm_llama_model]
        conn = get_connection("agents")
        row = conn.execute(
            "SELECT weight FROM reader_weights WHERE reader_name = ?",
            ("llm_finetuned",),
        ).fetchone()
        conn.close()
        assert row["weight"] == 0.05

    def test_gate_passthrough_when_enabled(self, tmp_path, monkeypatch):
        _init(tmp_path, monkeypatch)
        from ecis.config.settings import settings
        from ecis.extraction.finetuned_guard import apply_finetuned_gate

        set_threshold("use_finetuned_adapter", 1.0)
        models = [settings.llm_finetuned_model]
        assert apply_finetuned_gate("finetuned", models) == models
        assert apply_finetuned_gate("llama", models) == models


class TestCorporateActions:
    def test_dividend_invalidates_cache(self, monkeypatch):
        import pytest

        pytest.importorskip("yfinance")
        import pandas as pd
        import ecis.scoring.outcome_resolver as mod
        from ecis.scoring.outcome_resolver import _had_corporate_action

        class FakeTicker:
            splits = pd.Series(dtype=float)
            dividends = pd.Series([0.5], index=pd.DatetimeIndex(["2021-06-01"]))

        monkeypatch.setattr(mod.yf, "Ticker", lambda _ticker: FakeTicker())
        assert _had_corporate_action("TICKER", date(2021, 1, 1)) is True
        assert _had_corporate_action("TICKER", date(2022, 1, 1)) is False
