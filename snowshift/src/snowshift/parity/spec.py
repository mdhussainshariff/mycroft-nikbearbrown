"""What to compare, and how, for each migrated table.

The spec is explicit rather than introspected. Introspecting both catalogues
sounds tidier, but the two sides disagree about types in exactly the places a
migration goes wrong -- a DECIMAL(19,4) that landed as a FLOAT compares equal
under naive introspection and then silently drifts. Declaring the intent means
a type change shows up as a diff instead of disappearing into it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

#: How a column is aggregated. Every function here exists, with the same
#: semantics, on both SQL Server and Snowflake -- that is the whole selection
#: criterion.
NUMERIC_AGGS = ("count", "sum", "min", "max")
OTHER_AGGS = ("count", "min", "max")


class SpecError(RuntimeError):
    """The parity spec is missing or malformed."""


@dataclass(frozen=True)
class ColumnCheck:
    """One column and the aggregates to compare on it."""

    name: str
    kind: str = "text"  # numeric | text | date
    scale: int = 4  # decimal places SUM is rounded to, numeric only

    @property
    def aggregates(self) -> tuple[str, ...]:
        return NUMERIC_AGGS if self.kind == "numeric" else OTHER_AGGS


@dataclass(frozen=True)
class TableCheck:
    """One table, its source and target names, and its columns."""

    table: str
    source: str
    target: str
    key: str = ""
    columns: tuple[ColumnCheck, ...] = field(default_factory=tuple)

    @property
    def has_columns(self) -> bool:
        return bool(self.columns)


def load_spec(path: str | Path) -> list[TableCheck]:
    """Read a parity spec file into TableCheck objects."""
    spec_path = Path(path)
    if not spec_path.is_file():
        raise SpecError(f"no parity spec at {spec_path}")

    try:
        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SpecError(f"{spec_path} is not valid YAML: {exc}") from exc

    source_schema = raw.get("source_schema", "dbo")
    target_schema = raw.get("target_schema", "Planning")

    tables = raw.get("tables") or []
    if not tables:
        raise SpecError(f"{spec_path} declares no tables")

    checks: list[TableCheck] = []
    for entry in tables:
        name = entry.get("name")
        if not name:
            raise SpecError("every table entry needs a name")

        columns = []
        for col in entry.get("columns") or []:
            if isinstance(col, str):
                columns.append(ColumnCheck(col))
                continue
            col_name = col.get("name")
            if not col_name:
                raise SpecError(f"table {name!r} has a column with no name")
            kind = col.get("kind", "text")
            if kind not in ("numeric", "text", "date"):
                raise SpecError(
                    f"table {name!r} column {col_name!r}: "
                    f"kind must be numeric, text or date (got {kind!r})"
                )
            columns.append(ColumnCheck(col_name, kind, int(col.get("scale", 4))))

        checks.append(
            TableCheck(
                table=name,
                source=entry.get("source") or f"{source_schema}.{name}",
                target=entry.get("target") or f"{target_schema}.{name}",
                key=entry.get("key", ""),
                columns=tuple(columns),
            )
        )
    return checks
