# snowshift

> A SQL Server to Snowflake migration of a financial planning schema, plus the tooling to lint it, deploy it in dependency order, and prove the data landed intact.

The migration itself is the easy half. The hard half is the three questions that
follow it: *will this even run?*, *in what order?*, and *did the numbers survive?*
This repository answers all three with a command each.

```
snowshift lint      before you deploy  -- find T-SQL that Snowflake will reject
snowshift deploy    the cutover itself -- run the manifest in dependency order
snowshift parity    after you deploy   -- prove the data matches the source
```

The linter is not decorative. Run against the migrated SQL in this repo it found
a `SELECT TOP 10` that had survived conversion and would have failed on the first
execution — [see below](#what-the-linter-caught).

---

## Repository layout

```
snowshift/
├── README.md               ← you are here
├── manifest.yaml           ← deployment order: the single source of truth
├── parity.yaml             ← what to compare between source and target
├── pyproject.toml
│
├── sql/                    ← the migration, one object per file
│   ├── 00_setup/           ←   warehouse, database, schema, role grants
│   ├── 10_tables/          ←   8 core tables, dependency-ordered
│   ├── 20_staging/         ←   3 staging tables replacing SQL Server TVPs
│   ├── 30_views/           ←   2 reporting views
│   ├── 40_functions/       ←   2 scalar + 2 table-valued functions
│   ├── 50_procedures/      ←   6 business procedures
│   ├── 60_seed/            ←   ~400 sample rows (optional stage)
│   └── 90_tests/           ←   object verification + procedure smoke tests
│
├── src/snowshift/
│   ├── cli.py              ←   the three subcommands
│   ├── lint/
│   │   ├── rules.py        ←   27 dialect rules, each with a Snowflake fix
│   │   └── linter.py       ←   comment-aware scanner with noqa support
│   ├── deploy/
│   │   ├── manifest.py     ←   manifest parsing + stage selection
│   │   └── runner.py       ←   ordered execution, dry-run, failure halting
│   └── parity/
│       ├── spec.py         ←   declared (not introspected) comparison spec
│       └── compare.py      ←   portable aggregate queries + the differ
│
├── tests/                  ← 96 tests, no database required
└── docs/
    ├── migration-notes.md  ←   every T-SQL construct that had to change, and why
    └── architecture.md     ←   why the tooling is shaped this way
```

---

## What was migrated

A financial planning schema — budgeting, cost allocation, intercompany
consolidation — moved from SQL Server to Snowflake.

| Object type | Count | Notes |
|---|---:|---|
| Core tables | 8 | `FiscalPeriod` → `ConsolidationJournalLine`, in dependency order |
| Staging tables | 3 | stand-ins for table-valued parameters, which Snowflake has no equivalent for |
| Views | 2 | budget consolidation summary, allocation rule targets |
| Functions | 4 | 2 scalar, 2 table-valued |
| Procedures | 8 | 6 business procedures + 2 staging utilities |
| **Total objects** | **25** | across 29 SQL files, ~2,000 lines |

The conversions that were not mechanical — XML columns to `VARIANT`, computed
columns, recursive CTEs for hierarchy walks, `MERGE` semantics — are written up
in [`docs/migration-notes.md`](docs/migration-notes.md).

### Why one object per file

The migration originally arrived as a single 1,244-line `Main.sql` plus a folder
of procedure files that had drifted out of sync with it. Everything here is split
one-object-per-file and ordered by `manifest.yaml`, which means a failed
deployment names the object that failed rather than a line number in a monolith,
and re-running after a fix does not re-execute the 24 objects that already
succeeded.

The split was verified lossless: all 32 `CREATE` statements in the original
appear exactly once across the 29 files.

---

## Setup

```bash
git clone https://github.com/mdhussainshariff/snowshift.git
cd snowshift

pip install -e .            # lint + dry-run deploy, no database drivers needed
pip install -e '.[deploy]'  # adds the Snowflake connector
pip install -e '.[parity]'  # adds pyodbc for the source side
pip install -e '.[dev]'     # adds pytest

cp .env.example .env        # fill in only what the command you want needs
```

`snowshift lint` and `snowshift deploy --dry-run` deliberately work with no
credentials and no database drivers installed, so they run in CI on a bare image.

---

## Usage

### Lint

```bash
snowshift lint sql/                    # errors + warnings (default)
snowshift lint sql/ --severity error   # only what will fail to compile
snowshift lint sql/ --format json      # for CI
snowshift lint --list-rules
```

Findings carry the fix, not just the complaint:

```
sql/60_seed/01_sample_data.sql:343:1: ERROR SS008 SELECT TOP n is not Snowflake syntax.
    found: SELECT TOP 10
    fix:   Use SELECT ... LIMIT n.
```

Three severities. `error` will not compile; `warning` compiles but means
something different; `info` is a benign difference, off by default because it
fires on nearly every DDL line.

Suppress a line with `-- noqa` or `-- noqa: SS008`.

| | |
|---|---|
| Comments | blanked before matching, so a migration note describing a conversion never trips the rule it describes |
| String literals | **not** blanked — Snowflake procedure bodies live inside quoted strings, and that body is exactly what needs checking |

### Deploy

```bash
snowshift deploy --dry-run                     # plan, no connection needed
snowshift deploy                               # setup → procedures
snowshift deploy --include-optional            # also seed + tests
snowshift deploy --only procedures             # one stage
snowshift deploy --from views --through tests
snowshift deploy --continue-on-error
```

```
  tables
    [  ok  ] 01_FiscalPeriod.sql                             3 stmt   0.41s
    [  ok  ] 02_GLAccount.sql                                3 stmt   0.38s
    [ FAIL ] 03_CostCenter.sql                               0 stmt   0.12s
             002003 (42S02): SQL compilation error: Object 'PLANNING.FISCALPERIOD'
    [ skip ] 04_AllocationRule.sql
```

A failure halts the run by default and marks everything after it `skip`, because
in a dependency-ordered deployment the failures that follow the first one are
noise. `--continue-on-error` when you want the full picture.

Statement splitting is delegated to the Snowflake connector's own
`split_statements`, which understands `$$`-quoted procedure bodies. A hand-rolled
splitter would break on the first procedure containing a semicolon in its body —
which is all of them.

### Parity

```bash
snowshift parity                  # compare both sides
snowshift parity --show-sql       # emit the queries, run them by hand
snowshift parity --format json
snowshift parity --tolerance 0.01
```

For each table in `parity.yaml`: row count, plus `COUNT`/`SUM`/`MIN`/`MAX` per
declared column. Every aggregate used exists with identical semantics on both
engines — that is the entire selection criterion.

```
[  ok  ] FiscalPeriod                          36 rows  16 metrics
[ DIFF ] BudgetLineItem                   1 mismatch(es)
  BudgetLineItem.finalamount__sum
      source: 4820113.5500
      target: 4820113.0000  (delta 0.55)
```

That delta is the signature of a `DECIMAL(19,4)` that landed as an integer type —
the failure mode a row count alone will never surface.

Columns are **declared, not introspected**, on purpose. Introspecting both
catalogues sounds tidier, but the two sides disagree about types in exactly the
places a migration goes wrong: a `DECIMAL(19,4)` that became a `FLOAT` compares
equal under naive introspection and then drifts silently. Declaring the intent
turns that into a visible diff.

**What it does not catch:** two rows that swapped values between them, since the
aggregates are order-independent by design. Row-level hashing would catch it and
is the natural next step; it is deliberately absent because doing it portably
across two engines needs per-type canonicalisation rules worth writing only once
the aggregate pass is clean.

---

## What the linter caught

Run over the migration in this repo, the linter found two things in the seed
script that had survived conversion:

| Finding | Verdict |
|---|---|
| `SELECT TOP 10` at `01_sample_data.sql:343` | **Real.** Would have failed on execution. Fixed to `ORDER BY ... LIMIT 10`. |
| `N'...'` prefix at `01_sample_data.sql:103` | **False positive.** The value `'SALES-N', 'Sales - North'` matched at the hyphen boundary. The rule was re-anchored on what may legally precede the `N`, and both cases are now regression tests. |

The SQL in this repo is clean at `--severity warning`, and a test asserts it stays
that way.

---

## Testing

```bash
pytest                      # 96 tests, ~0.5s, no database
pytest --cov=snowshift
```

No test touches a database. The deploy runner is exercised through a fake
connection, and the parity differ takes already-fetched rows rather than a cursor
— which is why `compare_rows` has the signature it does.

Four of the tests are guardrails on the migration itself rather than on the code:

- the shipped SQL stays clean at `--severity warning`
- every `.sql` file on disk is claimed by a manifest stage (an unreferenced file
  would silently never deploy)
- `tables` precedes `views` and `procedures`; `setup` is first
- `seed` and `tests` stay optional, so a production cutover cannot load 400 rows
  of sample data

---

## Configuration

| Variable | Needed for | Description |
|---|---|---|
| `SNOWFLAKE_ACCOUNT` | deploy, parity | Account identifier |
| `SNOWFLAKE_USER` | deploy, parity | Username |
| `SNOWFLAKE_PASSWORD` | deploy, parity | Password — omit when using SSO |
| `SNOWFLAKE_ROLE` | deploy, parity | Role to assume |
| `SNOWFLAKE_AUTHENTICATOR` | optional | `externalbrowser` for SSO/MFA |
| `SOURCE_ODBC_DSN` | parity | ODBC connection string for the SQL Server source |
| `SNOWSHIFT_DATABASE` | optional | Overrides `manifest.yaml` |
| `SNOWSHIFT_SCHEMA` | optional | Overrides `manifest.yaml` |
| `SNOWSHIFT_WAREHOUSE` | optional | Overrides `manifest.yaml` |

Environment wins over `manifest.yaml` so CI can retarget a deployment without
editing a tracked file.

---

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Clean — no findings, no failures |
| `1` | Findings or deployment failures |
| `2` | Usage error — bad stage name, missing config, malformed manifest |

```yaml
- run: snowshift lint sql/ --severity error
- run: snowshift deploy --dry-run
```

---

## License

MIT — see [LICENSE](LICENSE).
