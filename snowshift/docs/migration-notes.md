# Migration notes

Every SQL Server construct in this schema that had no direct Snowflake
equivalent, what it became, and what that costs.

The mechanical conversions (`NVARCHAR` → `VARCHAR`, `GETDATE()` →
`CURRENT_TIMESTAMP()`, `ISNULL` → `COALESCE`) are enforced by
`snowshift lint` and are not repeated here. This document covers the ones where
a judgement call was made.

---

## Type mappings

| SQL Server | Snowflake | Note |
|---|---|---|
| `NVARCHAR(n)` / `NCHAR(n)` | `VARCHAR(n)` | Snowflake strings are Unicode; length is a soft limit |
| `DATETIME` / `DATETIME2` | `TIMESTAMP_NTZ` | No offset is stored — see *Timezones* below |
| `UNIQUEIDENTIFIER` | `VARCHAR(36)` | Default `UUID_STRING()` |
| `MONEY` / `SMALLMONEY` | `NUMBER(19,4)` | Preserves scale; `MONEY` has 4 decimal places |
| `BIGINT IDENTITY` | `INT AUTOINCREMENT` | Both resolve to `NUMBER(38,0)` |
| `XML` | `VARIANT` | Holds JSON — see *XML to VARIANT* below |
| `HIERARCHYID` | `INT` self-reference | See *Hierarchies* below |
| `ROWVERSION` | `TIMESTAMP_NTZ` | Not a true concurrency token — see *Optimistic concurrency* |
| `VARBINARY(MAX)` / `FILESTREAM` | external stage reference | Binary payloads move to stage storage |

---

## XML to VARIANT

`AllocationRule.TargetSpecification` and `BudgetHeader.BudgetMetadata` were
`XML` columns queried with `.nodes()` and `.value()`.

```sql
-- SQL Server
SELECT t.c.value('@CostCenterID', 'INT')
FROM AllocationRule r
CROSS APPLY r.TargetSpecification.nodes('/Targets/Target') AS t(c);

-- Snowflake
SELECT t.value:CostCenterID::INT
FROM Planning.AllocationRule r,
     LATERAL FLATTEN(input => r.TargetSpecification:Targets) t;
```

| Changed | Consequence |
|---|---|
| `CROSS APPLY .nodes()` | → `LATERAL FLATTEN()` |
| `.value('@attr', 'TYPE')` | → `:key::TYPE` |
| XQuery predicates | → JSON path syntax |
| Primary XML indexes | Dropped — Snowflake indexes VARIANT sub-columns automatically |

**The cost:** attribute order and XML namespaces are not preserved. Anything
that depended on document order must sort explicitly.

---

## Table-valued parameters

SQL Server TVPs have no Snowflake equivalent at all. Three procedures took them:
`USP_BulkImportBudgetData`, `USP_ExecuteCostAllocation`, and the hierarchy
processing path.

Three options were on the table:

| Option | Chosen | Why |
|---|---|---|
| Persistent staging table | **yes** | Batch-scoped, inspectable after a failure, works from any client |
| `VARIANT` / JSON array argument | partly | Used for `PROCESS_HIERARCHY_JSON`, where payloads are small |
| `COPY INTO` from a stage | no | Adds a file-staging step the callers do not have |

The staging tables live in [`sql/20_staging/`](../sql/20_staging) and each
carries a `StagingBatchID` so concurrent callers do not collide.

**The cost:** the TVP was transaction-scoped and vanished on rollback. A staging
table does not — `CLEANUP_ALLOCATION_RESULTS` exists to sweep abandoned batches,
and it must actually be scheduled.

---

## Computed columns

Snowflake has no persisted computed columns. Four were affected:

| Table | Column | Was | Now |
|---|---|---|---|
| `BudgetHeader` | `IsLocked` | computed from `StatusCode` | regular column, set on write |
| `BudgetLineItem` | — | persisted computed | regular column |
| `ConsolidationJournal` | `IsBalanced` | computed from line sums | regular column |
| `ConsolidationJournalLine` | `NetAmount` | `DebitAmount - CreditAmount` | regular column |

**The cost:** these can now be wrong. In SQL Server the engine guaranteed
`NetAmount = DebitAmount - CreditAmount`; here that is an invariant maintained by
the procedures that write the row. `snowshift parity` compares all three amount
columns on `ConsolidationJournalLine` precisely because a drift between them is
no longer structurally impossible.

---

## Hierarchies

`CostCenter` used `HIERARCHYID` with computed `HierarchyLevel` and `NodePath`
columns.

Replaced with a `ParentCostCenterID` self-reference plus a recursive CTE
(`tvf_ExplodeCostCenterHierarchy`). `HierarchyID` methods — `GetAncestor()`,
`IsDescendantOf()`, `GetLevel()` — become CTE predicates.

**The cost:** `IsDescendantOf()` was an index seek. The recursive CTE is a scan
per level. Fine at this cardinality (hundreds of cost centres); revisit if it
grows by orders of magnitude.

---

## Indexes

Every index in the source was dropped. Snowflake has no user-defined indexes.

| Source construct | Replacement |
|---|---|
| Clustered index | `CLUSTER BY` on the table |
| Nonclustered index | nothing — micro-partition pruning |
| Columnstore index | nothing — storage is already columnar |
| Filtered index | a `WHERE` clause at the query site |
| `INCLUDE` columns | nothing — columnar storage makes this meaningless |
| `IGNORE_DUP_KEY` | removed; duplicates must be handled in the procedure |

`CLUSTER BY` was kept only where the access pattern justified it, e.g.
`FiscalPeriod CLUSTER BY (FiscalYear, FiscalMonth)`. Clustering keys cost
credits to maintain and are not a free substitute for an index.

---

## Views

`SCHEMABINDING` does not exist; Snowflake views track their dependencies
automatically. Indexed views map to `MATERIALIZED VIEW`, though both views here
are left as standard views — materialising them was not justified at this size.

`COUNT_BIG(*)` → `COUNT(*)`, since every Snowflake integer is already 38 digits.

---

## Constraints

Snowflake **declares** `PRIMARY KEY`, `FOREIGN KEY` and `UNIQUE` but does not
**enforce** them. Only `NOT NULL` is enforced.

They are kept in the DDL because the query optimiser uses them and because they
document intent — but nothing stops a bad insert. This is the single largest
behavioural difference in the migration: constraint violations that SQL Server
rejected at write time now land silently and surface as a diff in
`snowshift parity`, if at all.

`CHECK` constraints are likewise accepted and not enforced.

---

## Optimistic concurrency

`ROWVERSION` was a monotonic per-database counter that made
`WHERE RowVersion = @expected` a reliable compare-and-swap.

`RowVersionTimestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()` is **not** that.
Two writes inside the same clock tick produce the same value. Any caller relying
on rowversion for optimistic locking needs a real sequence.

---

## Timezones

`TIMESTAMP_NTZ` stores no offset, matching the source `DATETIME2` behaviour. It
is the right mapping for a lift-and-shift, and it means the session timezone
never silently shifts a stored value.

Consequence: `CURRENT_TIMESTAMP()` returns session-local time, so a procedure run
from a differently configured session writes a differently-meaning value.
`SYSDATE()` (always UTC) is the fix where it matters.

---

## Procedures

All six business procedures became Snowflake Scripting (`LANGUAGE SQL`),
returning `VARIANT` via `OBJECT_CONSTRUCT` rather than output parameters.

| T-SQL | Snowflake Scripting |
|---|---|
| `RAISERROR` / `THROW` | `EXCEPTION` declarations with `RAISE` |
| `@@ROWCOUNT` | `SQLROWCOUNT` |
| `sp_executesql` | `EXECUTE IMMEDIATE` |
| `PRINT` | returned in the result `VARIANT` |
| Output parameters | a single `VARIANT` return value |
| `@variable` | `v_variable`, referenced as `:v_variable` |

None of the procedures use `MERGE`. Rule `SS106` still flags any that appear:
Snowflake raises an error when one target row matches several source rows,
where SQL Server picks one nondeterministically.

The duplicate-key risk that does apply here is the unenforced constraints
described [above](#constraints). Two procedures depended on SQL Server
rejecting duplicates and were changed to check for themselves:

- **`usp_BulkImportBudgetData`** relied on the natural-key `UNIQUE` on
  `BudgetLineItem`. It now rejects keys repeated within a payload, and handles
  lines that already exist according to `DUPLICATE_HANDLING`: `REJECT` refuses
  them, `UPDATE` overwrites them. Without this, running an import twice would
  double the budget. (The converted procedure also never resolved the
  payload's account, cost center and period codes to IDs, so it imported
  nothing at all. That is fixed too.)
- **`usp_ExecuteCostAllocation`** and **`usp_ProcessBudgetConsolidation`**
  read back the new journal's ID with `MAX(JournalID)`, standing in for
  `SCOPE_IDENTITY()`. That returns the wrong journal once two runs overlap,
  and `AUTOINCREMENT` is not guaranteed to be ordered. Their journal numbers
  were also only unique to the second. Each run now gets a journal number with
  a random suffix (`ALLOC-20260101120000-1a2b3c4d`) and is read back by that
  number. Header and lines are written in a single transaction. Rule `SS107`
  flags the `MAX(...ID)` read-back pattern.

The remaining exposure is concurrency: two imports into the same budget at the
same moment can both pass the existence check. SQL Server's constraint caught
that; nothing in Snowflake does short of serialising the imports.

---

## Not migrated

| Construct | Status |
|---|---|
| Triggers | None existed |
| Temporal (system-versioned) tables | Dropped — use Time Travel |
| `ROWGUIDCOL` / merge replication | Dropped |
| SQL Agent jobs | Out of scope — schedule with Snowflake Tasks |
| Linked servers | Out of scope |
