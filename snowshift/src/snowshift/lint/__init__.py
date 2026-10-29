"""T-SQL dialect linting for SQL destined for Snowflake."""

from snowshift.lint.linter import Finding, lint_paths, lint_text, select_rules
from snowshift.lint.rules import RULES, Rule

__all__ = ["Finding", "Rule", "RULES", "lint_paths", "lint_text", "select_rules"]
