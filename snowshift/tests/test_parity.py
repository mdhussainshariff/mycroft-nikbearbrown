"""Parity spec loading, query generation, and the comparison logic.

The comparison is tested without either database by feeding `compare_rows` the
rows a driver would have returned -- which is why that function takes rows
rather than a cursor.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from snowshift.parity import (
    ColumnCheck,
    SpecError,
    TableCheck,
    build_query,
    compare_rows,
    load_spec,
)
from snowshift.parity.compare import ParityReport, run_parity


@pytest.fixture
def spec_file(tmp_path):
    p = tmp_path / "parity.yaml"
    p.write_text(
        "source_schema: dbo\n"
        "target_schema: Planning\n"
        "tables:\n"
        "  - name: BudgetLineItem\n"
        "    key: BudgetLineItemID\n"
        "    columns:\n"
        "      - {name: FinalAmount, kind: numeric, scale: 4}\n"
        "      - {name: Notes, kind: text}\n",
        encoding="utf-8",
    )
    return p


class TestSpec:
    def test_schemas_default_the_qualified_names(self, spec_file):
        (check,) = load_spec(spec_file)
        assert check.source == "dbo.BudgetLineItem"
        assert check.target == "Planning.BudgetLineItem"

    def test_bare_string_column_defaults_to_text(self, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text("tables:\n  - name: T\n    columns: [Name]\n", encoding="utf-8")
        (check,) = load_spec(p)
        assert check.columns[0] == ColumnCheck("Name", "text", 4)

    def test_numeric_columns_get_a_sum_aggregate(self, spec_file):
        (check,) = load_spec(spec_file)
        amount, notes = check.columns
        assert "sum" in amount.aggregates
        assert "sum" not in notes.aggregates

    def test_unknown_kind_is_rejected(self, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text(
            "tables:\n  - name: T\n    columns:\n      - {name: C, kind: blob}\n",
            encoding="utf-8",
        )
        with pytest.raises(SpecError, match="kind must be"):
            load_spec(p)

    def test_missing_file_is_reported(self, tmp_path):
        with pytest.raises(SpecError, match="no parity spec"):
            load_spec(tmp_path / "gone.yaml")

    def test_empty_table_list_is_rejected(self, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text("tables: []\n", encoding="utf-8")
        with pytest.raises(SpecError, match="no tables"):
            load_spec(p)


class TestQueryGeneration:
    @pytest.fixture
    def check(self):
        return TableCheck(
            table="T",
            source="dbo.T",
            target="Planning.T",
            columns=(ColumnCheck("Amount", "numeric", 4), ColumnCheck("Name", "text")),
        )

    def test_both_dialects_agree_on_row_count(self, check):
        for dialect, table in (("sqlserver", check.source), ("snowflake", check.target)):
            assert "COUNT(*) AS row_count" in build_query(check, table, dialect)

    def test_sqlserver_uses_decimal_and_snowflake_uses_number(self, check):
        assert "DECIMAL(38, 4)" in build_query(check, check.source, "sqlserver")
        assert "NUMBER(38, 4)" in build_query(check, check.target, "snowflake")

    def test_the_two_queries_select_identical_aliases(self, check):
        """Aliases are the join key for the diff, so they must not drift."""

        def aliases(sql):
            return [
                ln.split(" AS ")[-1].rstrip(",")
                for ln in sql.splitlines()
                if not ln.startswith("FROM ")
            ]

        assert aliases(build_query(check, check.source, "sqlserver")) == aliases(
            build_query(check, check.target, "snowflake")
        )

    def test_text_columns_get_no_sum(self, check):
        assert "Name__sum" not in build_query(check, check.source, "sqlserver")

    def test_queries_target_the_right_table(self, check):
        assert build_query(check, check.source, "sqlserver").endswith("FROM dbo.T")
        assert build_query(check, check.target, "snowflake").endswith("FROM Planning.T")


class TestComparison:
    CHECK = TableCheck(table="T", source="dbo.T", target="Planning.T")
    COLUMNS = ["row_count", "amount__sum", "name__min"]

    def test_identical_rows_match(self):
        row = (100, Decimal("5000.0000"), "alpha")
        result = compare_rows(self.CHECK, row, row, self.COLUMNS)
        assert result.matched
        assert result.metrics_compared == 3

    def test_decimal_scale_difference_is_not_a_diff(self):
        # 5000 and 5000.0000 are the same number; only the rendering differs.
        src = (100, Decimal("5000"), "alpha")
        tgt = (100, Decimal("5000.0000"), "alpha")
        assert compare_rows(self.CHECK, src, tgt, self.COLUMNS).matched

    def test_missing_rows_are_reported(self):
        src = (100, Decimal("5000"), "alpha")
        tgt = (97, Decimal("5000"), "alpha")
        result = compare_rows(self.CHECK, src, tgt, self.COLUMNS)
        assert not result.matched
        assert result.diffs[0].metric == "row_count"
        assert result.source_rows == 100 and result.target_rows == 97

    def test_lost_decimal_scale_is_reported_with_a_delta(self):
        src = (100, Decimal("5000.5500"), "alpha")
        tgt = (100, Decimal("5000.0000"), "alpha")
        (diff,) = compare_rows(self.CHECK, src, tgt, self.COLUMNS).diffs
        assert diff.metric == "amount__sum"
        assert diff.delta == "0.55"

    def test_tolerance_absorbs_float_noise(self):
        src = (100, Decimal("5000.00001"), "alpha")
        tgt = (100, Decimal("5000.00002"), "alpha")
        assert compare_rows(self.CHECK, src, tgt, self.COLUMNS).matched

    def test_tolerance_does_not_absorb_a_real_difference(self):
        src = (100, Decimal("5000.00"), "alpha")
        tgt = (100, Decimal("5000.01"), "alpha")
        assert not compare_rows(self.CHECK, src, tgt, self.COLUMNS).matched

    def test_text_is_compared_exactly_apart_from_trailing_space(self):
        # SQL Server pads CHAR columns; that padding is not a migration defect.
        src = (100, Decimal("1"), "alpha   ")
        tgt = (100, Decimal("1"), "alpha")
        assert compare_rows(self.CHECK, src, tgt, self.COLUMNS).matched

    def test_truncated_text_is_reported(self):
        src = (100, Decimal("1"), "alphabet")
        tgt = (100, Decimal("1"), "alpha")
        (diff,) = compare_rows(self.CHECK, src, tgt, self.COLUMNS).diffs
        assert diff.metric == "name__min"

    def test_null_on_one_side_only_is_reported(self):
        src = (100, Decimal("1"), "alpha")
        tgt = (100, Decimal("1"), None)
        (diff,) = compare_rows(self.CHECK, src, tgt, self.COLUMNS).diffs
        assert diff.target == "NULL"

    def test_null_on_both_sides_matches(self):
        row = (100, Decimal("1"), None)
        assert compare_rows(self.CHECK, row, row, self.COLUMNS).matched


class FakeCursor:
    """Returns a canned row per query, and records the SQL it was given."""

    def __init__(self, row, columns):
        self.row, self.columns, self.seen = row, columns, []

    def execute(self, sql):
        self.seen.append(sql)

    def fetchone(self):
        return self.row

    @property
    def description(self):
        return [(c,) for c in self.columns]


class TestRunParity:
    COLUMNS = ["row_count", "finalamount__sum"]

    def test_matching_sides_produce_a_clean_report(self):
        check = TableCheck("T", "dbo.T", "Planning.T",
                           columns=(ColumnCheck("FinalAmount", "numeric"),))
        row = (10, Decimal("99.5"))
        report = run_parity([check], FakeCursor(row, self.COLUMNS),
                            FakeCursor(row, self.COLUMNS))
        assert report.ok
        assert "1/1 table(s) match" in report.as_text()

    def test_a_query_failure_is_captured_not_raised(self):
        class Exploding(FakeCursor):
            def execute(self, sql):
                raise RuntimeError("Object 'dbo.T' does not exist")

        check = TableCheck("T", "dbo.T", "Planning.T")
        report = run_parity([check], Exploding(None, []), FakeCursor((1,), ["row_count"]))
        assert not report.ok
        assert "does not exist" in report.results[0].error

    def test_json_output_is_parseable(self):
        import json

        check = TableCheck("T", "dbo.T", "Planning.T")
        report = run_parity([check], FakeCursor((5,), ["row_count"]),
                            FakeCursor((5,), ["row_count"]))
        assert json.loads(report.as_json())[0]["table"] == "T"

    def test_empty_report_is_vacuously_ok(self):
        assert ParityReport().ok
