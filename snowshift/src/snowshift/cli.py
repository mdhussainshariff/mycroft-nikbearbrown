"""snowshift command line interface.

Three subcommands, one per phase of a migration:

    lint    before you deploy  -- find T-SQL that will not run on Snowflake
    deploy  the cutover itself -- run the manifest in dependency order
    parity  after you deploy   -- prove the data landed intact

Exit codes are meant for CI: 0 clean, 1 findings or failures, 2 bad usage.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

from snowshift import __version__
from snowshift.deploy.manifest import ManifestError, load_manifest
from snowshift.deploy.runner import connect, deploy
from snowshift.lint.linter import format_findings, lint_paths
from snowshift.lint.rules import RULES
from snowshift.parity.compare import run_parity
from snowshift.parity.spec import SpecError, load_spec

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snowshift",
        description="Tooling for the SQL Server to Snowflake migration.",
    )
    parser.add_argument("--version", action="version", version=f"snowshift {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- lint ------------------------------------------------------------
    lint = sub.add_parser(
        "lint", help="Find T-SQL constructs that will not run on Snowflake."
    )
    lint.add_argument(
        "paths", nargs="*", default=["sql"], type=Path,
        help="Files or directories to scan (default: sql).",
    )
    lint.add_argument(
        "--severity", choices=("error", "warning", "info"), default="warning",
        help="Lowest severity to report (default: warning).",
    )
    lint.add_argument("--format", choices=("text", "json"), default="text")
    lint.add_argument(
        "--list-rules", action="store_true", help="Print every rule and exit."
    )

    # --- deploy ----------------------------------------------------------
    dep = sub.add_parser("deploy", help="Run the manifest against Snowflake.")
    dep.add_argument("--manifest", default="manifest.yaml", type=Path)
    dep.add_argument(
        "--dry-run", action="store_true",
        help="Print the execution plan without connecting to Snowflake.",
    )
    dep.add_argument("--only", help="Run exactly one stage.")
    dep.add_argument("--from", dest="from_", help="Start at this stage.")
    dep.add_argument("--through", help="Stop after this stage.")
    dep.add_argument(
        "--include-optional", action="store_true",
        help="Also run stages marked optional (seed, tests).",
    )
    dep.add_argument(
        "--continue-on-error", action="store_true",
        help="Keep going after a file fails instead of skipping the rest.",
    )
    dep.add_argument("--verbose", "-v", action="store_true")

    # --- parity ----------------------------------------------------------
    par = sub.add_parser("parity", help="Compare source and target after a cutover.")
    par.add_argument("--spec", default="parity.yaml", type=Path)
    par.add_argument("--format", choices=("text", "json"), default="text")
    par.add_argument(
        "--tolerance", default="0.0001",
        help="Absolute tolerance for numeric metrics (default: 0.0001).",
    )
    par.add_argument(
        "--show-sql", action="store_true",
        help="Print the generated queries instead of running them.",
    )

    return parser


def cmd_lint(args) -> int:
    if args.list_rules:
        for rule in RULES:
            print(f"{rule.code}  {rule.severity:<8} {rule.message}")
            print(f"          {rule.remedy}")
        return EXIT_OK

    missing = [p for p in args.paths if not p.exists()]
    if missing:
        print(f"no such path: {', '.join(str(p) for p in missing)}", file=sys.stderr)
        return EXIT_USAGE

    findings = lint_paths(args.paths, min_severity=args.severity)
    print(format_findings(findings, args.format))
    return EXIT_FINDINGS if findings else EXIT_OK


def cmd_deploy(args) -> int:
    try:
        manifest = load_manifest(args.manifest)
        stages = manifest.select(
            only=args.only,
            from_=args.from_,
            through=args.through,
            include_optional=args.include_optional,
        )
    except ManifestError as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if not stages:
        print("nothing selected; pass --include-optional to run seed/tests.")
        return EXIT_OK

    connection = None
    if not args.dry_run:
        missing = [v for v in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER") if not os.environ.get(v)]
        if missing:
            print(
                f"missing environment variable(s): {', '.join(missing)}\n"
                "See .env.example, or use --dry-run to plan without connecting.",
                file=sys.stderr,
            )
            return EXIT_USAGE
        try:
            connection = connect(
                account=os.environ["SNOWFLAKE_ACCOUNT"],
                user=os.environ["SNOWFLAKE_USER"],
                password=os.environ.get("SNOWFLAKE_PASSWORD"),
                role=os.environ.get("SNOWFLAKE_ROLE"),
                authenticator=os.environ.get("SNOWFLAKE_AUTHENTICATOR"),
                warehouse=manifest.warehouse,
                database=manifest.database,
                schema=manifest.schema,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"could not connect: {exc}", file=sys.stderr)
            return EXIT_FINDINGS

    try:
        result = deploy(
            manifest,
            stages,
            connection=connection,
            dry_run=args.dry_run,
            stop_on_error=not args.continue_on_error,
            on_event=(lambda m: print(f"  .. {m}")) if args.verbose else (lambda m: None),
        )
    finally:
        if connection is not None:
            connection.close()

    print(result.summary())
    return EXIT_OK if result.ok else EXIT_FINDINGS


def cmd_parity(args) -> int:
    try:
        checks = load_spec(args.spec)
    except SpecError as exc:
        print(f"spec error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.show_sql:
        from snowshift.parity.compare import build_query

        for check in checks:
            print(f"-- {check.table}: source")
            print(build_query(check, check.source, "sqlserver") + ";\n")
            print(f"-- {check.table}: target")
            print(build_query(check, check.target, "snowflake") + ";\n")
        return EXIT_OK

    source_conn, target_conn = _open_parity_connections()
    if source_conn is None or target_conn is None:
        return EXIT_USAGE

    try:
        report = run_parity(
            checks,
            source_conn.cursor(),
            target_conn.cursor(),
            tolerance=Decimal(args.tolerance),
        )
    finally:
        source_conn.close()
        target_conn.close()

    print(report.as_json() if args.format == "json" else report.as_text())
    return EXIT_OK if report.ok else EXIT_FINDINGS


def _open_parity_connections():
    """Open both sides, reporting clearly which one is not configured."""
    dsn = os.environ.get("SOURCE_ODBC_DSN")
    if not dsn:
        print(
            "SOURCE_ODBC_DSN is not set -- parity needs a live source database.\n"
            "Use --show-sql to emit the comparison queries and run them by hand.",
            file=sys.stderr,
        )
        return None, None

    try:
        import pyodbc
    except ImportError:
        print(
            "pyodbc is not installed. Install it with: pip install 'snowshift[parity]'",
            file=sys.stderr,
        )
        return None, None

    account, user = os.environ.get("SNOWFLAKE_ACCOUNT"), os.environ.get("SNOWFLAKE_USER")
    if not (account and user):
        print(
            "SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER must be set for the target side.",
            file=sys.stderr,
        )
        return None, None

    try:
        source = pyodbc.connect(dsn)
    except Exception as exc:  # noqa: BLE001
        print(f"could not connect to source: {exc}", file=sys.stderr)
        return None, None

    try:
        target = connect(
            account=account,
            user=user,
            password=os.environ.get("SNOWFLAKE_PASSWORD"),
            role=os.environ.get("SNOWFLAKE_ROLE"),
            authenticator=os.environ.get("SNOWFLAKE_AUTHENTICATOR"),
            warehouse=os.environ.get("SNOWSHIFT_WAREHOUSE"),
            database=os.environ.get("SNOWSHIFT_DATABASE"),
            schema=os.environ.get("SNOWSHIFT_SCHEMA"),
        )
    except Exception as exc:  # noqa: BLE001
        source.close()
        print(f"could not connect to target: {exc}", file=sys.stderr)
        return None, None

    return source, target


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return {"lint": cmd_lint, "deploy": cmd_deploy, "parity": cmd_parity}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
