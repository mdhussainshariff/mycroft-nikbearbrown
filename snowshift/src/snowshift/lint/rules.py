"""The T-SQL constructs that do not survive the move to Snowflake.

Each rule is a regex plus the Snowflake equivalent. Severity separates the two
failure modes that matter during a migration:

``error``   the statement will not compile on Snowflake at all -- a loud break.
``warning`` the statement compiles but means something different, or silently
            degrades. These are the expensive ones, so they are still reported
            by default; ``--severity error`` narrows to the loud set.
``info``    a benign difference worth knowing about. Off by default because it
            fires on nearly every DDL line; ``--severity info`` opts in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """A single dialect check."""

    code: str
    pattern: re.Pattern[str]
    message: str
    remedy: str
    severity: str = "error"

    def finditer(self, line: str):
        return self.pattern.finditer(line)


def _r(code, regex, message, remedy, severity="error", flags=re.IGNORECASE):
    return Rule(code, re.compile(regex, flags), message, remedy, severity)


#: Ordered so the most common SnowConvert leftovers surface first.
RULES: tuple[Rule, ...] = (
    # --- Will not compile -----------------------------------------------
    _r("SS001", r"\bGETDATE\s*\(\s*\)",
       "GETDATE() is T-SQL only.",
       "Use CURRENT_TIMESTAMP()."),
    _r("SS002", r"\bGETUTCDATE\s*\(\s*\)",
       "GETUTCDATE() is T-SQL only.",
       "Use SYSDATE(), which Snowflake returns in UTC."),
    _r("SS003", r"\bISNULL\s*\(",
       "ISNULL() is T-SQL only.",
       "Use IFNULL() or COALESCE()."),
    # Anchored on what may precede the N, so a value such as 'SALES-N', 'x'
    # is not mistaken for a literal prefix.
    _r("SS004", r"(?:^|(?<=[\s(,=+|]))N'(?:[^']|'')*'",
       "Unicode literal prefix N'...' is not valid Snowflake syntax.",
       "Drop the N prefix; Snowflake strings are Unicode already."),
    _r("SS005", r"\[[A-Za-z_][\w ]*\]",
       "Bracket-quoted identifier.",
       'Use double quotes, or drop the quoting entirely if the name needs none.'),
    _r("SS006", r"@@ROWCOUNT",
       "@@ROWCOUNT has no Snowflake equivalent in this form.",
       "Use SQLROWCOUNT inside a Snowflake Scripting block."),
    _r("SS007", r"@@IDENTITY|\bSCOPE_IDENTITY\s*\(\s*\)",
       "@@IDENTITY / SCOPE_IDENTITY() are not available.",
       "Select MAX(id) inside the transaction, or use a Snowflake SEQUENCE."),
    _r("SS008", r"\bSELECT\s+TOP\s+\(?\s*\d+",
       "SELECT TOP n is not Snowflake syntax.",
       "Use SELECT ... LIMIT n."),
    _r("SS009", r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)",
       "IDENTITY(seed, increment) is not Snowflake syntax.",
       "Use AUTOINCREMENT (START n INCREMENT m)."),
    _r("SS010", r"\bNVARCHAR\s*\(|\bNCHAR\s*\(|\bNTEXT\b",
       "N-prefixed character types do not exist in Snowflake.",
       "Use VARCHAR -- it is Unicode and the length is a soft limit."),
    _r("SS011", r"\bDATETIME2?\b(?!_)",
       "DATETIME / DATETIME2 are not Snowflake types.",
       "Use TIMESTAMP_NTZ (or TIMESTAMP_TZ if the column carries an offset)."),
    _r("SS012", r"\bUNIQUEIDENTIFIER\b",
       "UNIQUEIDENTIFIER is not a Snowflake type.",
       "Use VARCHAR(36) with UUID_STRING() as the default."),
    _r("SS013", r"\bMONEY\b|\bSMALLMONEY\b",
       "MONEY / SMALLMONEY are not Snowflake types.",
       "Use NUMBER(19,4) to keep the same scale."),
    _r("SS014", r"\bCREATE\s+(?:NON)?CLUSTERED\s+INDEX\b|\bCREATE\s+INDEX\b",
       "Snowflake has no user-defined indexes.",
       "Delete the statement; use CLUSTER BY on the table if pruning needs help."),
    _r("SS015", r"\bWITH\s*\(\s*NOLOCK\s*\)|\bNOLOCK\b",
       "NOLOCK is a T-SQL locking hint.",
       "Delete it; Snowflake readers never block writers."),
    _r("SS016", r"\bsp_executesql\b|\bEXEC\s*\(",
       "sp_executesql / EXEC() dynamic SQL is T-SQL only.",
       "Use EXECUTE IMMEDIATE inside a Snowflake Scripting block."),
    # BEGIN TRANSACTION itself is valid Snowflake, and inside a scripting block
    # it is the required spelling; only the T-SQL abbreviation is not.
    _r("SS017", r"\b(?:BEGIN|COMMIT|ROLLBACK)\s+TRAN\b",
       "TRAN is a T-SQL abbreviation.",
       "Spell it out: BEGIN TRANSACTION, COMMIT, ROLLBACK."),
    _r("SS018", r"\bPRINT\s+",
       "PRINT has no Snowflake equivalent.",
       "Return the value, or RAISE a notice from a scripting block."),
    _r("SS019", r"\bDATEADD\s*\(\s*(?:yy|yyyy|mm|m|dd|d|hh|mi|n|ss|s|ms)\b",
       "DATEADD with an abbreviated date part.",
       "Spell the part out: DATEADD(month, n, d)."),
    _r("SS020", r"\bCREATE\s+TYPE\b.*\bAS\s+TABLE\b",
       "Table-valued parameters do not exist in Snowflake.",
       "Replace with a staging table or a VARIANT/ARRAY argument."),

    # --- Compiles, but changes meaning ------------------------------------
    _r("SS101", r"\+\s*(?:N?'|\w+\s*\+)",
       "String concatenation with + is ambiguous in Snowflake.",
       "Use || or CONCAT() so numeric operands are not coerced.",
       severity="warning"),
    _r("SS102", r"\bTINYINT\b|\bSMALLINT\b|\bBIGINT\b|\bINT\b",
       "All integer aliases collapse to NUMBER(38,0) in Snowflake.",
       "Harmless, but declare NUMBER(p,0) if the width was a real constraint.",
       severity="info"),
    _r("SS103", r"\bCHARINDEX\s*\(",
       "CHARINDEX argument order differs from POSITION.",
       "Use POSITION(substr IN str) and re-check the argument order.",
       severity="warning"),
    _r("SS104", r"\bLEN\s*\(",
       "LEN() ignores trailing spaces in T-SQL; LENGTH() does not.",
       "Use LENGTH(), and TRIM() first if the old behaviour mattered.",
       severity="warning"),
    _r("SS105", r"\bTRUNCATE\s+TABLE\b",
       "TRUNCATE is not transactional the same way.",
       "Confirm the surrounding transaction still behaves as intended.",
       severity="warning"),
    _r("SS106", r"\bMERGE\b",
       "MERGE semantics differ on multi-match rows.",
       "Snowflake errors on multiple source matches unless ERROR_ON_NONDETERMINISTIC_MERGE=FALSE.",
       severity="warning"),
    # The usual stand-in for SCOPE_IDENTITY(). It returns another session's row
    # once two runs overlap, and AUTOINCREMENT is not guaranteed to be ordered.
    _r("SS107", r":=\s*\(\s*SELECT\s+MAX\s*\(\s*[\w.]*ID\s*\)|\bSELECT\s+MAX\s*\(\s*[\w.]*ID\s*\)\s+INTO\b",
       "Reading back a generated ID with MAX() is not safe.",
       "Write a value unique to this run (e.g. with UUID_STRING()) and look the row up by it.",
       severity="warning"),
)

RULES_BY_CODE = {rule.code: rule for rule in RULES}
