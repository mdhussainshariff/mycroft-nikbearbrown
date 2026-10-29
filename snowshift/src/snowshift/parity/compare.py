"""Compare a migrated table against its source and report what drifted.

The comparison is aggregate-based: row counts, plus COUNT/SUM/MIN/MAX per
declared column. That catches the defects a migration actually produces --
dropped rows, truncated strings, lost decimal scale, shifted timestamps --
without needing to stream both tables over the wire.

What it does not catch: two rows that swapped values between them, since the
aggregates are order-independent by design. Row-level hashing would catch that
and is the natural next step; it is deliberately not here, because doing it
portably across the two engines needs per-type canonicalisation rules that are
worth writing only once the aggregate pass is clean.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Sequence

from snowshift.parity.spec import TableCheck

#: Metric name -> (source value, target value) tolerance for float noise.
DEFAULT_TOLERANCE = Decimal("0.0001")


@dataclass(frozen=True)
class Diff:
    """One metric that did not match."""

    table: str
    metric: str
    source: str
    target: str
    delta: str = ""

    def as_text(self) -> str:
        delta = f"  (delta {self.delta})" if self.delta else ""
        return (
            f"  {self.table}.{self.metric}\n"
            f"      source: {self.source}\n"
            f"      target: {self.target}{delta}"
        )


@dataclass
class TableResult:
    """Outcome for one table."""

    table: str
    source_rows: int = 0
    target_rows: int = 0
    metrics_compared: int = 0
    diffs: list[Diff] = field(default_factory=list)
    error: str = ""

    @property
    def matched(self) -> bool:
        return not self.diffs and not self.error


@dataclass
class ParityReport:
    """Outcome for a whole run."""

    results: list[TableResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.matched for r in self.results)

    def as_text(self) -> str:
        lines = []
        for r in self.results:
            if r.error:
                lines.append(f"[ERROR] {r.table}: {r.error}")
                continue
            if r.matched:
                lines.append(
                    f"[  ok  ] {r.table:<32} {r.source_rows:>8,} rows  "
                    f"{r.metrics_compared} metrics"
                )
            else:
                lines.append(
                    f"[ DIFF ] {r.table:<32} {len(r.diffs)} mismatch(es)"
                )
                lines.extend(d.as_text() for d in r.diffs)

        matched = sum(1 for r in self.results if r.matched)
        errored = sum(1 for r in self.results if r.error)
        lines.append(
            f"\n{matched}/{len(self.results)} table(s) match"
            + (f", {errored} errored" if errored else "")
        )
        return "\n".join(lines)

    def as_json(self) -> str:
        return json.dumps([asdict(r) for r in self.results], indent=2, default=str)


def build_query(check: TableCheck, table_name: str, dialect: str) -> str:
    """Build the aggregate query for one side.

    Both dialects get the same aggregate functions; only the cast syntax and
    the quoting differ.
    """
    cast = "DECIMAL(38, {scale})" if dialect == "sqlserver" else "NUMBER(38, {scale})"

    selects = ["COUNT(*) AS row_count"]
    for col in check.columns:
        for agg in col.aggregates:
            alias = f"{col.name}__{agg}"
            if agg == "count":
                selects.append(f"COUNT({col.name}) AS {alias}")
            elif agg == "sum":
                typ = cast.format(scale=col.scale)
                selects.append(f"CAST(SUM(CAST({col.name} AS {typ})) AS {typ}) AS {alias}")
            else:  # min / max
                selects.append(f"{agg.upper()}({col.name}) AS {alias}")

    body = ",\n       ".join(selects)
    return f"SELECT {body}\nFROM {table_name}"


def _normalise(value: Any) -> str:
    """Render a value so the two engines' drivers compare on equal footing.

    Decimals are normalised so 100.0000 and 100 match; everything else is
    compared on its string form, which is what the drivers already agree on for
    dates and text.
    """
    if value is None:
        return "NULL"
    if isinstance(value, (Decimal, float)):
        d = Decimal(str(value)).normalize()
        # normalize() gives 1E+2 for 100; expand it back.
        return format(d, "f")
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value).rstrip()


def compare_rows(
    check: TableCheck,
    source_row: Sequence[Any],
    target_row: Sequence[Any],
    columns: Sequence[str],
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> TableResult:
    """Diff two already-fetched aggregate rows.

    Kept separate from the execution path so the comparison logic is testable
    without either database.
    """
    result = TableResult(table=check.table)

    src = dict(zip(columns, source_row))
    tgt = dict(zip(columns, target_row))

    result.source_rows = int(src.get("row_count") or 0)
    result.target_rows = int(tgt.get("row_count") or 0)

    for metric in columns:
        result.metrics_compared += 1
        s_raw, t_raw = src.get(metric), tgt.get(metric)

        # Numeric metrics get a tolerance; everything else is exact.
        if isinstance(s_raw, (Decimal, float, int)) and isinstance(
            t_raw, (Decimal, float, int)
        ) and not isinstance(s_raw, bool) and not isinstance(t_raw, bool):
            delta = abs(Decimal(str(s_raw)) - Decimal(str(t_raw)))
            if delta > tolerance:
                result.diffs.append(
                    Diff(check.table, metric, _normalise(s_raw), _normalise(t_raw),
                         format(delta.normalize(), "f"))
                )
            continue

        s, t = _normalise(s_raw), _normalise(t_raw)
        if s != t:
            result.diffs.append(Diff(check.table, metric, s, t))

    return result


def run_parity(
    checks: Sequence[TableCheck],
    source_cursor,
    target_cursor,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> ParityReport:
    """Execute the aggregate queries on both sides and diff the results."""
    report = ParityReport()

    for check in checks:
        try:
            source_cursor.execute(build_query(check, check.source, "sqlserver"))
            source_row = source_cursor.fetchone()
            columns = [d[0].lower() for d in source_cursor.description]

            target_cursor.execute(build_query(check, check.target, "snowflake"))
            target_row = target_cursor.fetchone()

            report.results.append(
                compare_rows(check, source_row, target_row, columns, tolerance)
            )
        except Exception as exc:  # noqa: BLE001 -- surfaced in the report
            report.results.append(
                TableResult(table=check.table, error=str(exc).strip().splitlines()[0][:200])
            )

    return report
