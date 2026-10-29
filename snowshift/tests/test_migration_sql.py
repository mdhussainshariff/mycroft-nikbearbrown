"""Guardrails on the migrated SQL itself.

These are the tests that stop a regression from being committed: the shipped
SQL must stay dialect-clean, and the manifest must keep covering all of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from snowshift.deploy.manifest import load_manifest
from snowshift.deploy.runner import deploy
from snowshift.lint import lint_paths

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql"


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(ROOT / "manifest.yaml")


def test_shipped_sql_has_no_dialect_errors():
    findings = lint_paths([SQL], min_severity="warning")
    assert not findings, "\n".join(f.as_text() for f in findings)


def test_every_sql_file_is_claimed_by_a_stage(manifest):
    """An unreferenced file would silently never deploy."""
    on_disk = {p.resolve() for p in SQL.rglob("*.sql")}
    in_manifest = {
        f.resolve() for stage in manifest.stages for f in stage.files()
    }
    assert on_disk == in_manifest


def test_every_stage_has_at_least_one_file(manifest):
    for stage in manifest.stages:
        assert stage.files(), f"stage {stage.name} is empty"


def test_full_dry_run_plans_cleanly(manifest):
    result = deploy(manifest, manifest.select(include_optional=True), dry_run=True)
    assert result.ok
    assert len(result.results) == len(list(SQL.rglob("*.sql")))


def test_tables_precede_the_views_that_read_them(manifest):
    names = [s.name for s in manifest.stages]
    assert names.index("tables") < names.index("views")
    assert names.index("tables") < names.index("procedures")
    assert names.index("setup") == 0


def test_seed_and_tests_are_optional(manifest):
    """A production cutover must not load 400 rows of sample data."""
    assert manifest.stage("seed").optional
    assert manifest.stage("tests").optional
    assert "seed" not in [s.name for s in manifest.select()]


def test_parity_spec_covers_every_core_table():
    from snowshift.parity import load_spec

    checked = {c.table for c in load_spec(ROOT / "parity.yaml")}
    on_disk = {
        p.stem.split("_", 1)[1] for p in (SQL / "10_tables").glob("*.sql")
    }
    assert on_disk <= checked, f"unchecked tables: {on_disk - checked}"
