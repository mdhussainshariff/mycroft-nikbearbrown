"""Scan .sql files for T-SQL constructs that will not survive on Snowflake.

Comments are blanked before matching, so the migration notes that describe a
conversion ("XML converted to VARIANT") never trip the rule they describe.
String literals are *not* blanked: Snowflake procedure bodies live inside
quoted strings, and that body is exactly what needs checking.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from snowshift.lint.rules import RULES, Rule

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

_NOQA = re.compile(r"--\s*noqa\b(?::\s*(?P<codes>[\w\s,]+))?", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    """One rule match at one position."""

    path: str
    line: int
    column: int
    code: str
    severity: str
    message: str
    remedy: str
    snippet: str

    def as_text(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.column}: "
            f"{self.severity.upper()} {self.code} {self.message}\n"
            f"    found: {self.snippet}\n"
            f"    fix:   {self.remedy}"
        )


def _blank_comments(text: str) -> str:
    """Replace comment characters with spaces, preserving every offset.

    Newlines are kept so line numbers stay correct.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "--":
            j = text.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def _suppressed(raw_line: str) -> set[str] | None:
    """Return codes suppressed on this line, or None if nothing is suppressed.

    A bare ``-- noqa`` suppresses everything and returns an empty set, which the
    caller treats as "skip this line".
    """
    match = _NOQA.search(raw_line)
    if not match:
        return None
    codes = match.group("codes")
    if not codes:
        return set()
    return {c.strip().upper() for c in codes.split(",") if c.strip()}


def select_rules(
    rules: Sequence[Rule] = RULES, min_severity: str = "warning"
) -> list[Rule]:
    """The rules at or above a severity, most severe first."""
    cutoff = SEVERITY_ORDER[min_severity]
    return [r for r in rules if SEVERITY_ORDER[r.severity] <= cutoff]


def lint_text(
    text: str,
    path: str = "<string>",
    rules: Sequence[Rule] | None = None,
    min_severity: str = "warning",
) -> list[Finding]:
    """Lint one SQL document.

    ``rules`` is the explicit rule set; when omitted, the default set is
    filtered by ``min_severity`` so this matches what ``lint_paths`` reports.
    """
    if rules is None:
        rules = select_rules(RULES, min_severity)

    raw_lines = text.splitlines()
    scan_lines = _blank_comments(text).splitlines()
    findings: list[Finding] = []

    for lineno, scan_line in enumerate(scan_lines, start=1):
        if not scan_line.strip():
            continue
        raw_line = raw_lines[lineno - 1]
        suppressed = _suppressed(raw_line)
        if suppressed is not None and not suppressed:
            continue  # bare noqa

        for rule in rules:
            if suppressed and rule.code in suppressed:
                continue
            for match in rule.finditer(scan_line):
                findings.append(
                    Finding(
                        path=path,
                        line=lineno,
                        column=match.start() + 1,
                        code=rule.code,
                        severity=rule.severity,
                        message=rule.message,
                        remedy=rule.remedy,
                        snippet=raw_line.strip()[:120],
                    )
                )
                break  # one finding per rule per line keeps output readable

    return findings


def lint_paths(
    paths: Iterable[Path],
    rules: Sequence[Rule] = RULES,
    min_severity: str = "warning",
) -> list[Finding]:
    """Lint every .sql file under the given files or directories."""
    selected = select_rules(rules, min_severity)

    findings: list[Finding] = []
    for sql_file in sorted(_iter_sql(paths)):
        text = sql_file.read_text(encoding="utf-8-sig", errors="replace")
        findings.extend(lint_text(text, str(sql_file), selected))

    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.path, f.line, f.column))
    return findings


def _iter_sql(paths: Iterable[Path]):
    for p in paths:
        if p.is_dir():
            yield from p.rglob("*.sql")
        elif p.suffix.lower() == ".sql":
            yield p


def format_findings(findings: Sequence[Finding], fmt: str = "text") -> str:
    """Render findings as human-readable text or machine-readable JSON."""
    if fmt == "json":
        return json.dumps([asdict(f) for f in findings], indent=2)

    if not findings:
        return "No dialect issues found."

    blocks = [f.as_text() for f in findings]
    counts = Counter(f.severity for f in findings)
    tally = ", ".join(
        f"{counts[sev]} {sev}" for sev in SEVERITY_ORDER if counts.get(sev)
    )
    blocks.append(
        f"\n{tally} across {len({f.path for f in findings})} file(s)."
    )
    return "\n\n".join(blocks)
