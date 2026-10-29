"""Execute a manifest against Snowflake, one file at a time.

Statement splitting is delegated to the Snowflake connector's own
``execute_string``, which already understands ``$$``-quoted procedure bodies.
Hand-rolling a splitter here would break on the first procedure that contains a
semicolon inside its body -- which is all of them.

The connector is imported lazily so that ``snowshift lint`` and ``--dry-run``
work on a machine that has never installed it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from snowshift.deploy.manifest import Manifest, Stage


@dataclass
class FileResult:
    """Outcome of one .sql file."""

    stage: str
    path: Path
    status: str  # ok | failed | skipped
    statements: int = 0
    seconds: float = 0.0
    error: str = ""
    exact_count: bool = True

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "skipped")


@dataclass
class DeployResult:
    """Outcome of a whole run."""

    dry_run: bool
    results: list[FileResult] = field(default_factory=list)

    @property
    def failed(self) -> list[FileResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        lines = []
        current = None
        for r in self.results:
            if r.stage != current:
                current = r.stage
                lines.append(f"\n  {current}")
            mark = {"ok": "  ok  ", "failed": " FAIL ", "skipped": " skip "}[r.status]
            timing = f"{r.seconds:6.2f}s" if r.seconds else "       "
            count = f"{r.statements:3d}" if r.exact_count else f"~{r.statements:<2d}"
            lines.append(f"    [{mark}] {r.path.name:<45} {count} stmt {timing}")
            if r.error:
                lines.append(f"             {r.error}")

        ok = sum(1 for r in self.results if r.status == "ok")
        failed = len(self.failed)
        skipped = sum(1 for r in self.results if r.status == "skipped")
        head = "DRY RUN (nothing executed)" if self.dry_run else "Deployment"
        lines.append(f"\n{head}: {ok} ok, {failed} failed, {skipped} skipped")
        if self.dry_run and any(not r.exact_count for r in self.results):
            lines.append(
                "  '~' counts are approximate: install "
                "snowflake-connector-python for exact statement splitting."
            )
        return "\n".join(lines)


def _count_statements(sql: str) -> tuple[int, bool]:
    """Statement count for the dry-run report, and whether it is exact.

    Without the connector installed there is no reliable splitter, so fall back
    to counting semicolons and mark the number approximate. That fallback
    over-counts procedures badly (every semicolon inside a body counts), which
    is exactly why the report flags it rather than presenting it as fact.
    """
    try:
        from io import StringIO

        from snowflake.connector.util_text import split_statements

        return sum(1 for _ in split_statements(StringIO(sql), remove_comments=True)), True
    except Exception:
        return max(1, sql.count(";")), False


def deploy(
    manifest: Manifest,
    stages: Sequence[Stage],
    connection=None,
    dry_run: bool = False,
    stop_on_error: bool = True,
    on_event: Callable[[str], None] = lambda msg: None,
) -> DeployResult:
    """Run the selected stages.

    ``connection`` is an open Snowflake connection. When ``dry_run`` is set it
    is never touched, so passing None is fine.
    """
    result = DeployResult(dry_run=dry_run)

    if not dry_run:
        if connection is None:
            raise ValueError("a live connection is required unless dry_run=True")
        _set_context(connection, manifest)

    halted = False
    for stage in stages:
        for sql_file in stage.files():
            if halted:
                result.results.append(FileResult(stage.name, sql_file, "skipped"))
                continue

            sql = sql_file.read_text(encoding="utf-8-sig")
            if dry_run:
                count, exact = _count_statements(sql)
                result.results.append(
                    FileResult(stage.name, sql_file, "ok", count, exact_count=exact)
                )
                on_event(f"would run {sql_file}")
                continue

            started = time.monotonic()
            try:
                executed = 0
                for cursor in connection.execute_string(sql, remove_comments=False):
                    executed += 1
                    cursor.close()
                result.results.append(
                    FileResult(
                        stage.name, sql_file, "ok", executed, time.monotonic() - started
                    )
                )
                on_event(f"ran {sql_file} ({executed} statements)")
            except Exception as exc:  # noqa: BLE001 -- surfaced in the report
                result.results.append(
                    FileResult(
                        stage.name,
                        sql_file,
                        "failed",
                        seconds=time.monotonic() - started,
                        error=str(exc).strip().splitlines()[0][:200],
                    )
                )
                on_event(f"FAILED {sql_file}: {exc}")
                if stop_on_error:
                    halted = True

    return result


def _set_context(connection, manifest: Manifest) -> None:
    """Pin warehouse/database/schema before the first file runs.

    The setup stage creates these, so failures here are expected on a cold
    account and are not fatal.
    """
    for statement in (
        f"USE WAREHOUSE {manifest.warehouse}" if manifest.warehouse else "",
        f"USE DATABASE {manifest.database}" if manifest.database else "",
        f"USE SCHEMA {manifest.schema}" if manifest.schema else "",
    ):
        if not statement:
            continue
        try:
            with connection.cursor() as cur:
                cur.execute(statement)
        except Exception:
            pass  # setup stage will create it


def connect(
    account: str,
    user: str,
    password: str | None = None,
    role: str | None = None,
    warehouse: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    authenticator: str | None = None,
):
    """Open a Snowflake connection, importing the connector only when needed."""
    try:
        import snowflake.connector
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "snowflake-connector-python is not installed. "
            "Install it with: pip install 'snowshift[deploy]'"
        ) from exc

    kwargs = {
        "account": account,
        "user": user,
        "role": role,
        "warehouse": warehouse,
        "database": database,
        "schema": schema,
    }
    if authenticator:
        kwargs["authenticator"] = authenticator
    else:
        kwargs["password"] = password
    return snowflake.connector.connect(**{k: v for k, v in kwargs.items() if v})
