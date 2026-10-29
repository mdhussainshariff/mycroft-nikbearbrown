"""Linter behaviour: what it catches, and just as importantly what it does not."""

from __future__ import annotations

import pytest

from snowshift.lint import lint_text
from snowshift.lint.linter import format_findings
from snowshift.lint.rules import RULES


def codes(sql: str) -> set[str]:
    return {f.code for f in lint_text(sql)}


@pytest.mark.parametrize(
    "code, sql",
    [
        ("SS001", "SELECT GETDATE();"),
        ("SS002", "SELECT GETUTCDATE();"),
        ("SS003", "SELECT ISNULL(a, 0) FROM t;"),
        ("SS004", "INSERT INTO t VALUES (N'text');"),
        ("SS005", "SELECT * FROM [dbo].[Orders];"),
        ("SS006", "SELECT @@ROWCOUNT;"),
        ("SS007", "SELECT SCOPE_IDENTITY();"),
        ("SS008", "SELECT TOP 10 a FROM t;"),
        ("SS009", "CREATE TABLE t (id INT IDENTITY(1,1));"),
        ("SS010", "CREATE TABLE t (n NVARCHAR(50));"),
        ("SS011", "CREATE TABLE t (d DATETIME2);"),
        ("SS012", "CREATE TABLE t (g UNIQUEIDENTIFIER);"),
        ("SS013", "CREATE TABLE t (m MONEY);"),
        ("SS014", "CREATE NONCLUSTERED INDEX ix ON t (a);"),
        ("SS015", "SELECT * FROM t WITH (NOLOCK);"),
        ("SS016", "EXEC sp_executesql @sql;"),
        ("SS017", "BEGIN TRAN;"),
        ("SS017", "COMMIT TRAN;"),
        ("SS018", "PRINT 'hello';"),
        ("SS019", "SELECT DATEADD(mm, 1, d);"),
        ("SS020", "CREATE TYPE BudgetRows AS TABLE (id INT);"),
    ],
)
def test_each_error_rule_fires(code, sql):
    assert code in codes(sql)


@pytest.mark.parametrize(
    "code, sql",
    [
        ("SS103", "SELECT CHARINDEX('a', b);"),
        ("SS104", "SELECT LEN(name) FROM t;"),
        ("SS105", "TRUNCATE TABLE t;"),
        ("SS106", "MERGE INTO t USING s ON t.id = s.id;"),
        ("SS107", "v_id := (SELECT MAX(JournalID) FROM j WHERE t = 'A');"),
        ("SS107", "SELECT MAX(OrderID) INTO :v_id FROM orders;"),
    ],
)
def test_each_warning_rule_fires(code, sql):
    assert code in codes(sql)


class TestComments:
    """Migration notes describe conversions; they must not trip the rule."""

    def test_line_comment_is_ignored(self):
        assert codes("-- GETDATE() was replaced with CURRENT_TIMESTAMP()") == set()

    def test_block_comment_is_ignored(self):
        assert codes("/*\n  ISNULL -> COALESCE\n  NVARCHAR(50) -> VARCHAR\n*/") == set()

    def test_code_after_block_comment_still_scanned(self):
        assert "SS001" in codes("/* note */ SELECT GETDATE();")

    def test_line_numbers_survive_comment_blanking(self):
        sql = "/* a\n   b\n   c */\nSELECT GETDATE();"
        (finding,) = lint_text(sql)
        assert finding.line == 4


class TestProcedureBodies:
    """Bodies live inside string literals, so literals are deliberately scanned."""

    def test_body_inside_dollar_quotes_is_scanned(self):
        sql = "CREATE PROCEDURE p() AS $$\nBEGIN\n  SELECT GETDATE();\nEND;\n$$;"
        assert "SS001" in codes(sql)

    def test_body_inside_single_quotes_is_scanned(self):
        sql = "CREATE PROCEDURE p() AS '\nBEGIN\n  SELECT ISNULL(a,0);\nEND;\n';"
        assert "SS003" in codes(sql)


class TestNoqa:
    def test_bare_noqa_suppresses_everything(self):
        assert codes("SELECT GETDATE(), ISNULL(a,0); -- noqa") == set()

    def test_targeted_noqa_suppresses_only_that_code(self):
        found = codes("SELECT GETDATE(), ISNULL(a,0); -- noqa: SS001")
        assert "SS001" not in found
        assert "SS003" in found

    def test_noqa_is_line_scoped(self):
        sql = "SELECT GETDATE(); -- noqa\nSELECT GETDATE();"
        (finding,) = lint_text(sql)
        assert finding.line == 2


class TestFalsePositives:
    """Regressions found by running the linter over the real migration."""

    def test_n_suffix_in_a_string_value_is_not_a_unicode_prefix(self):
        # 'SALES-N', 'x' used to match the N'...' rule at the hyphen boundary.
        assert "SS004" not in codes("INSERT INTO t VALUES ('SALES-N', 'Sales North');")

    def test_genuine_n_prefix_still_caught_on_the_same_shape(self):
        assert "SS004" in codes("INSERT INTO t VALUES (N'x'), ('SALES-N', 'y');")

    def test_timestamp_ntz_is_not_flagged_as_datetime(self):
        assert "SS011" not in codes("CREATE TABLE t (c TIMESTAMP_NTZ);")

    def test_spelled_out_begin_transaction_is_valid_snowflake(self):
        # Required inside scripting blocks; only the T-SQL "TRAN" is foreign.
        assert "SS017" not in codes("BEGIN TRANSACTION;")


class TestSeverityFiltering:
    def test_info_rules_are_excluded_by_default(self):
        # SS102 (integer aliases) is info; it must not appear at warning level.
        assert "SS102" not in codes("CREATE TABLE t (a INT);")

    def test_every_rule_declares_a_known_severity(self):
        assert {r.severity for r in RULES} <= {"error", "warning", "info"}

    def test_rule_codes_are_unique(self):
        codes_seen = [r.code for r in RULES]
        assert len(codes_seen) == len(set(codes_seen))


class TestOutput:
    def test_clean_input_reports_clean(self):
        assert format_findings([]) == "No dialect issues found."

    def test_summary_counts_by_actual_severity(self):
        summary = format_findings(lint_text("SELECT GETDATE(), LEN(x) FROM t;"))
        assert "1 error, 1 warning" in summary

    def test_json_output_is_parseable(self):
        import json

        parsed = json.loads(format_findings(lint_text("SELECT GETDATE();"), "json"))
        assert parsed[0]["code"] == "SS001"
        assert parsed[0]["line"] == 1


class TestIdReadBack:
    """SS107 targets assigning MAX(id) to a variable, not every MAX()."""

    def test_reporting_max_is_not_flagged(self):
        assert "SS107" not in codes("SELECT MAX(JournalID) AS last_id FROM j;")

    def test_max_of_non_id_column_is_not_flagged(self):
        assert "SS107" not in codes("v_total := (SELECT MAX(Amount) FROM t);")

