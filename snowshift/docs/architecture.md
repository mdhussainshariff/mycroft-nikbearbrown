# Architecture

Why the tooling is shaped the way it is. Each section is a decision that could
reasonably have gone the other way.

---

## The three commands map to the three failure modes

A migration fails in three distinct ways, at three distinct times:

| When | Failure | Command |
|---|---|---|
| Before deploy | SQL that Snowflake will not compile | `lint` |
| During deploy | objects created in the wrong order, or half-created | `deploy` |
| After deploy | everything ran, and the numbers are wrong | `parity` |

They are separate commands because they have separate prerequisites. `lint`
needs no credentials and no drivers. `deploy` needs Snowflake. `parity` needs
both databases live at once — which, in a real cutover, is a narrow window.
Folding them into one command would drag the strictest prerequisite onto all
three.

---

## The base install has no database drivers

`pyproject.toml` declares only `PyYAML` as a hard dependency. The Snowflake
connector and `pyodbc` are extras.

This is what makes `snowshift lint` and `snowshift deploy --dry-run` runnable on
a bare CI image with `pip install -e .` and no credentials — which in turn is
what makes it plausible that they actually run on every commit. A linter that
needs a database is a linter nobody runs.

The connector is imported lazily inside `runner.connect()` and
`_count_statements()`, so the absence only bites at the point it is genuinely
needed.

---

## Statement splitting is delegated, not implemented

`runner.deploy()` calls the connector's `execute_string()`, which uses
Snowflake's own `split_statements`.

The alternative — splitting on semicolons — fails immediately. Every procedure
in this schema has a body like:

```sql
CREATE OR REPLACE PROCEDURE p() AS $$
DECLARE
    v_total NUMBER := 0;     -- semicolon
BEGIN
    SELECT ...;              -- semicolon
END;                         -- semicolon
$$;                          -- the only real statement boundary
```

A naive splitter produces six broken fragments. Writing a correct one means
implementing `$$`-quoting, `'`-quoting with `''` escapes, and comment handling —
a parser the connector already ships.

The visible consequence: `--dry-run` without the connector installed falls back
to counting semicolons, and says so by prefixing the count with `~`. An
approximate number labelled approximate is more useful than a precise-looking
wrong one.

---

## Ordering is a list, not a solver

`manifest.yaml` is a flat ordered list of directories. There is no dependency
graph, no topological sort.

The dependencies here are a straight line: setup → tables → staging → views →
functions → procedures. A solver would add a graph, a cycle check, and an error
class to express a constraint the directory numbering already expresses — and it
would hide the ordering from the reader, who currently gets it by looking at the
file.

If dependencies ever stop being linear, the list stops being adequate and the
solver earns its place. Not before.

---

## Failure halts by default

When a file fails, the runner marks every remaining file `skip` rather than
continuing.

In a dependency-ordered deployment the first failure causes most of what
follows. If `10_tables/01_FiscalPeriod.sql` fails, the eight objects referencing
it fail too, and a report with nine failures buries the one that matters.

`--continue-on-error` exists for when you want the full picture — typically a
first run against a fresh account, where you would rather collect every problem
in one pass.

---

## Comments are blanked; string literals are not

The linter blanks comments before matching, preserving offsets so line and
column numbers stay correct.

Without this, the migration notes trip the rules they describe: a comment reading
`-- XML converted to VARIANT` or `-- ISNULL replaced with COALESCE` would be
reported as a finding. The notes are the most rule-dense text in the repository.

String literals are deliberately **not** blanked, because Snowflake procedure
bodies live inside them:

```sql
CREATE OR REPLACE PROCEDURE p() AS '
    SELECT GETDATE();     -- inside a string literal, and genuinely broken
';
```

Blanking literals would skip every procedure body in the repo — the code most
likely to contain leftovers, since it is the code SnowConvert translates least
reliably.

The trade-off is false positives on data that happens to look like T-SQL. One
showed up in practice: `'SALES-N', 'Sales - North'` matched the `N'...'` rule at
the hyphen boundary. The rule was re-anchored on what may legally precede the
`N`; both the false positive and the true positive are now regression tests.

---

## Three severities, and `info` is off by default

| Severity | Meaning | Default |
|---|---|---|
| `error` | will not compile | reported |
| `warning` | compiles, means something different | reported |
| `info` | benign difference worth knowing | hidden |

`SS102` (all integer aliases collapse to `NUMBER(38,0)`) is accurate and fires
124 times across this repo — on essentially every DDL line. At `warning` it
would bury the two findings that mattered.

The severity split is not decorative. `--severity error` is the CI gate;
`--severity warning` is the review pass; `--severity info` is for someone
auditing type mappings on purpose.

---

## Parity columns are declared, not introspected

`parity.yaml` names each column and its kind. Reading both catalogues and
diffing automatically would be less typing.

It would also miss the defect it most needs to catch. A `DECIMAL(19,4)` that
landed as a `FLOAT` has the same column name on both sides; introspection
compares `SUM(col)` to `SUM(col)` and reports a match while the value quietly
drifts. Declaring `kind: numeric, scale: 4` makes the comparison assert the
intended type, so the drift becomes a diff.

The cost is maintenance: a new column is not checked until someone adds it. A
test asserts every table in `sql/10_tables/` appears in the spec, which catches
the table-level omission if not the column-level one.

---

## Parity aggregates over row hashing

Row counts plus `COUNT`/`SUM`/`MIN`/`MAX` per column. Every function used exists
with identical semantics on both engines — that is the entire selection
criterion, and it is why `AVG` and `STDDEV` are absent (rounding differs).

This catches dropped rows, truncated strings, lost decimal scale, and shifted
timestamps — the defects migrations actually produce — with one query per table
per side and no data crossing the wire.

It does not catch two rows swapping values, because the aggregates are
order-independent.

Row-level hashing would catch that, and the portable version is genuinely hard:
`MD5_NUMBER_LOWER64` on Snowflake returns unsigned, `CONVERT(BIGINT, HASHBYTES(...))`
on SQL Server returns signed, and the canonicalisation rules for dates, decimals
and NULLs have to match exactly on both sides or every row differs. That work is
worth doing once the aggregate pass is clean and the remaining question is
genuinely "did values swap". Not before.

---

## The comparison logic takes rows, not cursors

`compare_rows()` takes two already-fetched sequences. `run_parity()` is the thin
layer that executes queries and hands rows to it.

This is why the comparison logic — decimal normalisation, tolerance handling,
NULL semantics, trailing-space handling for `CHAR` padding — is covered by
fourteen tests that touch no database. The same split makes the deploy runner
testable through a fake connection.

If a function needs a live database to test, the interesting logic is usually in
the wrong place.

---

## Exit codes are the CI contract

| Code | Meaning |
|---:|---|
| `0` | clean |
| `1` | findings or failures — the tool worked, the migration has a problem |
| `2` | usage error — bad stage name, missing config, malformed manifest |

Separating `1` from `2` matters in a pipeline: a misspelled `--only` flag and a
genuinely failing deployment should not look the same to whoever reads the
build.
