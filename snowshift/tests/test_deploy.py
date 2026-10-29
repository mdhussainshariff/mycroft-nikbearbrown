"""Manifest parsing, stage selection, and the runner's ordering guarantees."""

from __future__ import annotations

import pytest

from snowshift.deploy.manifest import ManifestError, load_manifest
from snowshift.deploy.runner import deploy


@pytest.fixture
def manifest_file(tmp_path):
    """A three-stage manifest whose last stage is optional."""
    for stage, names in (
        ("a", ["02_second.sql", "01_first.sql"]),  # written out of order on purpose
        ("b", ["01_only.sql"]),
        ("c", ["01_opt.sql"]),
    ):
        d = tmp_path / stage
        d.mkdir()
        for n in names:
            (d / n).write_text("SELECT 1;", encoding="utf-8")

    path = tmp_path / "manifest.yaml"
    path.write_text(
        "target:\n"
        "  database: DB\n  schema: S\n  warehouse: WH\n"
        "stages:\n"
        "  - {name: a, path: a}\n"
        "  - {name: b, path: b}\n"
        "  - {name: c, path: c, optional: true}\n",
        encoding="utf-8",
    )
    return path


class TestLoading:
    def test_reads_target_and_stages(self, manifest_file):
        m = load_manifest(manifest_file)
        assert (m.database, m.schema, m.warehouse) == ("DB", "S", "WH")
        assert [s.name for s in m.stages] == ["a", "b", "c"]

    def test_stage_paths_resolve_relative_to_the_manifest(self, manifest_file):
        m = load_manifest(manifest_file)
        assert m.stage("a").path.is_dir()

    def test_environment_overrides_the_manifest(self, manifest_file, monkeypatch):
        monkeypatch.setenv("SNOWSHIFT_DATABASE", "OTHER")
        assert load_manifest(manifest_file).database == "OTHER"

    def test_missing_file_is_reported(self, tmp_path):
        with pytest.raises(ManifestError, match="no manifest"):
            load_manifest(tmp_path / "nope.yaml")

    def test_malformed_yaml_is_reported(self, tmp_path):
        p = tmp_path / "m.yaml"
        p.write_text("stages: [\n", encoding="utf-8")
        with pytest.raises(ManifestError, match="not valid YAML"):
            load_manifest(p)

    def test_empty_stage_list_is_rejected(self, tmp_path):
        p = tmp_path / "m.yaml"
        p.write_text("target: {}\nstages: []\n", encoding="utf-8")
        with pytest.raises(ManifestError, match="no stages"):
            load_manifest(p)

    def test_duplicate_stage_names_are_rejected(self, tmp_path):
        p = tmp_path / "m.yaml"
        p.write_text(
            "stages:\n  - {name: a, path: a}\n  - {name: a, path: b}\n", encoding="utf-8"
        )
        with pytest.raises(ManifestError, match="duplicate stage"):
            load_manifest(p)

    def test_stage_pointing_at_a_missing_directory_is_reported(self, tmp_path):
        p = tmp_path / "m.yaml"
        p.write_text("stages:\n  - {name: a, path: gone}\n", encoding="utf-8")
        with pytest.raises(ManifestError, match="missing directory"):
            load_manifest(p).stage("a").files()


class TestSelection:
    def test_optional_stages_are_excluded_by_default(self, manifest_file):
        m = load_manifest(manifest_file)
        assert [s.name for s in m.select()] == ["a", "b"]

    def test_include_optional_adds_them_back(self, manifest_file):
        m = load_manifest(manifest_file)
        assert [s.name for s in m.select(include_optional=True)] == ["a", "b", "c"]

    def test_only_picks_one_stage(self, manifest_file):
        assert [s.name for s in load_manifest(manifest_file).select(only="b")] == ["b"]

    def test_only_overrides_the_optional_exclusion(self, manifest_file):
        # Naming an optional stage explicitly is itself the opt-in.
        assert [s.name for s in load_manifest(manifest_file).select(only="c")] == ["c"]

    def test_through_is_inclusive(self, manifest_file):
        assert [s.name for s in load_manifest(manifest_file).select(through="a")] == ["a"]

    def test_from_is_inclusive(self, manifest_file):
        m = load_manifest(manifest_file)
        assert [s.name for s in m.select(from_="b", include_optional=True)] == ["b", "c"]

    def test_inverted_range_is_rejected(self, manifest_file):
        with pytest.raises(ManifestError, match="comes after"):
            load_manifest(manifest_file).select(from_="b", through="a")

    def test_unknown_stage_names_the_valid_ones(self, manifest_file):
        with pytest.raises(ManifestError, match="known stages: a, b, c"):
            load_manifest(manifest_file).select(only="zzz")


class TestFileOrdering:
    def test_files_run_in_filename_order_not_directory_order(self, manifest_file):
        files = load_manifest(manifest_file).stage("a").files()
        assert [f.name for f in files] == ["01_first.sql", "02_second.sql"]


class FakeCursor:
    def __init__(self):
        self.closed = False

    def execute(self, sql):
        return self

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeConnection:
    """Records what was executed; optionally fails on a named file's SQL."""

    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on
        self.executed: list[str] = []

    def cursor(self):
        return FakeCursor()

    def execute_string(self, sql, remove_comments=False):
        self.executed.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("syntax error at line 1")
        return [FakeCursor()]

    def close(self):
        pass


class TestRunner:
    def test_dry_run_never_touches_the_connection(self, manifest_file):
        m = load_manifest(manifest_file)
        result = deploy(m, m.select(), connection=None, dry_run=True)
        assert result.ok
        assert len(result.results) == 3
        assert result.dry_run

    def test_live_run_requires_a_connection(self, manifest_file):
        m = load_manifest(manifest_file)
        with pytest.raises(ValueError, match="live connection"):
            deploy(m, m.select(), connection=None, dry_run=False)

    def test_successful_run_executes_every_file(self, manifest_file):
        m = load_manifest(manifest_file)
        conn = FakeConnection()
        result = deploy(m, m.select(), connection=conn)
        assert result.ok
        assert len(conn.executed) == 3

    def test_failure_halts_and_marks_the_rest_skipped(self, manifest_file):
        m = load_manifest(manifest_file)
        # 01_first.sql is the first file of the first stage.
        (m.stage("a").path / "01_first.sql").write_text("BAD SQL;", encoding="utf-8")
        result = deploy(m, m.select(), connection=FakeConnection(fail_on="BAD SQL"))

        assert not result.ok
        assert [r.status for r in result.results] == ["failed", "skipped", "skipped"]
        assert "syntax error" in result.failed[0].error

    def test_continue_on_error_runs_the_remaining_files(self, manifest_file):
        m = load_manifest(manifest_file)
        (m.stage("a").path / "01_first.sql").write_text("BAD SQL;", encoding="utf-8")
        result = deploy(
            m,
            m.select(),
            connection=FakeConnection(fail_on="BAD SQL"),
            stop_on_error=False,
        )
        assert [r.status for r in result.results] == ["failed", "ok", "ok"]

    def test_summary_labels_a_dry_run_as_such(self, manifest_file):
        m = load_manifest(manifest_file)
        summary = deploy(m, m.select(), dry_run=True).summary()
        assert "DRY RUN" in summary
        assert "3 ok, 0 failed, 0 skipped" in summary
