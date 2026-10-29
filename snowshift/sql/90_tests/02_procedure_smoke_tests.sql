/*
================================================================================
PROCEDURE SMOKE TESTS
================================================================================

Financial Planning Schema - Comprehensive Procedure Testing

Tests all 6 business procedures against the seeded sample data.

Prerequisites:
1. snowshift deploy --through 50_procedures (schema created)
2. snowshift deploy --only 60_seed (data loaded)

Every test asserts on what the procedure did and RAISEs when it is wrong, so
a failure fails the deploy run and halts the remaining tests. Each block is
wrapped in EXECUTE IMMEDIATE $$ ... $$ because the connector's execute_string
cannot split a bare DECLARE ... BEGIN ... END block.

The sample budget is looked up by BudgetCode: its BudgetHeaderID is assigned by
AUTOINCREMENT and is not guaranteed to be 1.


================================================================================
TEST SETUP - Verify Schema and Data
================================================================================
*/

USE WAREHOUSE MIGRATION_WH;
USE DATABASE SNOWCONVERT_DEMO;
USE SCHEMA Planning;

SELECT '=== PROCEDURE SMOKE TESTS - WITH TESTSAMPLE DATA ===' AS StartMessage;



-- Verify TestSample data exists
SELECT '=== DATA VERIFICATION ===' AS Phase;

SELECT
    'FiscalPeriod' AS Table_Name,
    COUNT(*) AS Record_Count
FROM Planning.FiscalPeriod
UNION ALL
SELECT 'GLAccount', COUNT(*) FROM Planning.GLAccount
UNION ALL
SELECT 'CostCenter', COUNT(*) FROM Planning.CostCenter
UNION ALL
SELECT 'AllocationRule', COUNT(*) FROM Planning.AllocationRule
UNION ALL
SELECT 'BudgetHeader', COUNT(*) FROM Planning.BudgetHeader
UNION ALL
SELECT 'BudgetLineItem', COUNT(*) FROM Planning.BudgetLineItem
UNION ALL
SELECT 'ConsolidationJournal', COUNT(*) FROM Planning.ConsolidationJournal
UNION ALL
SELECT 'ConsolidationJournalLine', COUNT(*) FROM Planning.ConsolidationJournalLine
ORDER BY Table_Name;

/*
================================================================================
TEST 1: usp_BulkImportBudgetData
================================================================================

1a  Import three lines with UPDATE handling. The seed is random, so these keys
    may or may not already exist; UPDATE gives the same end state either way:
    exactly one line per key, carrying the imported amounts.
1b  Re-import the same payload with REJECT. Every row must be rejected and the
    budget must not grow -- the regression test for the unenforced natural-key
    UNIQUE constraint.
1c  Unknown codes and a key repeated within the payload are all rejected.
*/

SELECT '=== TEST 1: BULK IMPORT DATA ===' AS TestCase;

EXECUTE IMMEDIATE $$
DECLARE
    v_budget_id INT;
    v_payload VARIANT;
    v_result VARIANT;
    v_imported INT;
    v_rejected INT;
    v_lines_before INT;
    v_lines_after INT;
    v_matching_lines INT;
    v_final_amount DECIMAL(19,4);
    EX_FIRST_IMPORT EXCEPTION (-20901, 'TEST 1a failed: expected all 3 rows imported and none rejected');
    EX_NOT_ONE_LINE_PER_KEY EXCEPTION (-20902, 'TEST 1a failed: expected exactly one budget line per imported key');
    EX_WRONG_AMOUNT EXCEPTION (-20903, 'TEST 1a failed: FinalAmount for 4000/OPS is not original plus adjusted');
    EX_RERUN_NOT_REJECTED EXCEPTION (-20904, 'TEST 1b failed: re-import with REJECT should reject all 3 rows');
    EX_RERUN_DUPLICATED EXCEPTION (-20905, 'TEST 1b failed: re-import changed the number of budget lines');
    EX_BAD_ROWS_ACCEPTED EXCEPTION (-20906, 'TEST 1c failed: unknown codes and in-payload duplicates should all be rejected');
BEGIN
    v_budget_id := (SELECT BudgetHeaderID FROM Planning.BudgetHeader WHERE BudgetCode = 'BUDGET-2024-001');

    v_payload := PARSE_JSON('[
        {
            "account_number": "4000",
            "cost_center_code": "OPS",
            "fiscal_year": 2024,
            "fiscal_month": 4,
            "original_amount": 175000.00,
            "adjusted_amount": 8500.00,
            "spread_method_code": "EVEN",
            "notes": "Additional Product Revenue"
        },
        {
            "account_number": "5000",
            "cost_center_code": "SALES",
            "fiscal_year": 2024,
            "fiscal_month": 4,
            "original_amount": 85000.00,
            "adjusted_amount": -2500.00,
            "spread_method_code": "EVEN",
            "notes": "Salary adjustment"
        },
        {
            "account_number": "5200",
            "cost_center_code": "HR",
            "fiscal_year": 2024,
            "fiscal_month": 4,
            "original_amount": 25000.00,
            "adjusted_amount": 0,
            "spread_method_code": "EVEN",
            "notes": "Office rent"
        }
    ]');

    -- 1a
    CALL Planning.usp_BulkImportBudgetData(
        'VARIANT', :v_budget_id, NULL, :v_payload, NULL, 'LENIENT', 'UPDATE', 10000, TRUE
    ) INTO :v_result;

    v_imported := (SELECT :v_result:rows_imported::INT);
    v_rejected := (SELECT :v_result:rows_rejected::INT);
    IF (v_imported <> 3 OR v_rejected <> 0) THEN
        RAISE EX_FIRST_IMPORT;
    END IF;

    v_matching_lines := (
        SELECT COUNT(*)
        FROM Planning.BudgetLineItem bli
        JOIN Planning.GLAccount ga ON bli.GLAccountID = ga.GLAccountID
        JOIN Planning.CostCenter cc ON bli.CostCenterID = cc.CostCenterID
        JOIN Planning.FiscalPeriod fp ON bli.FiscalPeriodID = fp.FiscalPeriodID
        WHERE bli.BudgetHeaderID = :v_budget_id
        AND fp.FiscalYear = 2024
        AND fp.FiscalMonth = 4
        AND ga.AccountNumber || '/' || cc.CostCenterCode IN ('4000/OPS', '5000/SALES', '5200/HR')
    );
    IF (v_matching_lines <> 3) THEN
        RAISE EX_NOT_ONE_LINE_PER_KEY;
    END IF;

    v_final_amount := (
        SELECT bli.FinalAmount
        FROM Planning.BudgetLineItem bli
        JOIN Planning.GLAccount ga ON bli.GLAccountID = ga.GLAccountID
        JOIN Planning.CostCenter cc ON bli.CostCenterID = cc.CostCenterID
        JOIN Planning.FiscalPeriod fp ON bli.FiscalPeriodID = fp.FiscalPeriodID
        WHERE bli.BudgetHeaderID = :v_budget_id
        AND fp.FiscalYear = 2024
        AND fp.FiscalMonth = 4
        AND ga.AccountNumber = '4000'
        AND cc.CostCenterCode = 'OPS'
    );
    IF (v_final_amount IS NULL OR v_final_amount <> 183500) THEN
        RAISE EX_WRONG_AMOUNT;
    END IF;

    -- 1b
    v_lines_before := (SELECT COUNT(*) FROM Planning.BudgetLineItem WHERE BudgetHeaderID = :v_budget_id);

    CALL Planning.usp_BulkImportBudgetData(
        'VARIANT', :v_budget_id, NULL, :v_payload, NULL, 'LENIENT', 'REJECT', 10000, TRUE
    ) INTO :v_result;

    v_imported := (SELECT :v_result:rows_imported::INT);
    v_rejected := (SELECT :v_result:rows_rejected::INT);
    IF (v_imported <> 0 OR v_rejected <> 3) THEN
        RAISE EX_RERUN_NOT_REJECTED;
    END IF;

    v_lines_after := (SELECT COUNT(*) FROM Planning.BudgetLineItem WHERE BudgetHeaderID = :v_budget_id);
    IF (v_lines_after <> v_lines_before) THEN
        RAISE EX_RERUN_DUPLICATED;
    END IF;

    -- 1c
    v_payload := PARSE_JSON('[
        {"account_number": "9999", "cost_center_code": "OPS",   "fiscal_year": 2024, "fiscal_month": 5, "original_amount": 1000.00},
        {"account_number": "4000", "cost_center_code": "SALES", "fiscal_year": 2024, "fiscal_month": 5, "original_amount": 2000.00},
        {"account_number": "4000", "cost_center_code": "SALES", "fiscal_year": 2024, "fiscal_month": 5, "original_amount": 3000.00}
    ]');

    CALL Planning.usp_BulkImportBudgetData(
        'VARIANT', :v_budget_id, NULL, :v_payload, NULL, 'LENIENT', 'UPDATE', 10000, TRUE
    ) INTO :v_result;

    v_imported := (SELECT :v_result:rows_imported::INT);
    v_rejected := (SELECT :v_result:rows_rejected::INT);
    v_lines_after := (SELECT COUNT(*) FROM Planning.BudgetLineItem WHERE BudgetHeaderID = :v_budget_id);
    IF (v_imported <> 0 OR v_rejected <> 3 OR v_lines_after <> v_lines_before) THEN
        RAISE EX_BAD_ROWS_ACCEPTED;
    END IF;

    RETURN 'TEST 1 passed: import, re-import rejection and bad-row rejection';
END;
$$;

/*
================================================================================
TEST 2: usp_ExecuteCostAllocation
================================================================================

Exactly one new journal, its ID returned by the procedure, holding one line per
budget line and totalling what the procedure reports as allocated.
*/

SELECT '=== TEST 2: COST ALLOCATION ===' AS TestCase;

EXECUTE IMMEDIATE $$
DECLARE
    v_budget_id INT;
    v_result VARIANT;
    v_journal_id INT;
    v_journals_before INT;
    v_journals_after INT;
    v_expected_lines INT;
    v_actual_lines INT;
    v_line_total DECIMAL(19,4);
    v_reported_total DECIMAL(19,4);
    EX_NO_JOURNAL EXCEPTION (-20911, 'TEST 2 failed: procedure did not return the journal it created');
    EX_JOURNAL_COUNT EXCEPTION (-20912, 'TEST 2 failed: expected exactly one new allocation journal');
    EX_LINE_COUNT EXCEPTION (-20913, 'TEST 2 failed: journal lines do not match the budget lines');
    EX_LINE_TOTAL EXCEPTION (-20914, 'TEST 2 failed: journal line total does not match total_allocated');
BEGIN
    v_budget_id := (SELECT BudgetHeaderID FROM Planning.BudgetHeader WHERE BudgetCode = 'BUDGET-2024-001');
    v_journals_before := (
        SELECT COUNT(*) FROM Planning.ConsolidationJournal
        WHERE BudgetHeaderID = :v_budget_id AND JournalType = 'ALLOCATION'
    );

    CALL Planning.usp_ExecuteCostAllocation(:v_budget_id, 'HEADCOUNT', FALSE, FALSE) INTO :v_result;

    v_journal_id := (SELECT :v_result:journal_id::INT);
    IF (v_journal_id IS NULL) THEN
        RAISE EX_NO_JOURNAL;
    END IF;

    v_journals_after := (
        SELECT COUNT(*) FROM Planning.ConsolidationJournal
        WHERE BudgetHeaderID = :v_budget_id AND JournalType = 'ALLOCATION'
    );
    IF (v_journals_after <> v_journals_before + 1) THEN
        RAISE EX_JOURNAL_COUNT;
    END IF;

    v_expected_lines := (SELECT COUNT(*) FROM Planning.BudgetLineItem WHERE BudgetHeaderID = :v_budget_id);
    v_actual_lines := (SELECT COUNT(*) FROM Planning.ConsolidationJournalLine WHERE JournalID = :v_journal_id);
    IF (v_actual_lines <> v_expected_lines) THEN
        RAISE EX_LINE_COUNT;
    END IF;

    v_line_total := (SELECT COALESCE(SUM(NetAmount), 0) FROM Planning.ConsolidationJournalLine WHERE JournalID = :v_journal_id);
    v_reported_total := (SELECT :v_result:total_allocated::DECIMAL(19,4));
    IF (v_line_total <> v_reported_total) THEN
        RAISE EX_LINE_TOTAL;
    END IF;

    RETURN 'TEST 2 passed: one journal, ' || v_actual_lines || ' lines, total ' || v_line_total;
END;
$$;

/*
================================================================================
TEST 3: usp_GenerateRollingForecast
================================================================================

The procedure is still a placeholder: it counts periods and adds a flat 100000
per period without writing anything. This only pins the period count.
*/

SELECT '=== TEST 3: ROLLING FORECAST ===' AS TestCase;

EXECUTE IMMEDIATE $$
DECLARE
    v_budget_id INT;
    v_result VARIANT;
    v_periods INT;
    EX_PERIOD_COUNT EXCEPTION (-20921, 'TEST 3 failed: expected 12 forecast periods');
BEGIN
    v_budget_id := (SELECT BudgetHeaderID FROM Planning.BudgetHeader WHERE BudgetCode = 'BUDGET-2024-001');

    CALL Planning.usp_GenerateRollingForecast(
        :v_budget_id, 12, 2024, 1, 3.5, 'SEASONAL_FACTORS', TRUE
    ) INTO :v_result;

    v_periods := (SELECT :v_result:periods_generated::INT);
    IF (v_periods IS NULL OR v_periods <> 12) THEN
        RAISE EX_PERIOD_COUNT;
    END IF;

    RETURN 'TEST 3 passed: 12 periods (procedure is a placeholder)';
END;
$$;

/*
================================================================================
TEST 4: usp_PerformFinancialClose
================================================================================

Closing January 2024 must lock the period and mark its budget lines allocated.

validate_only is not tested: the procedure currently ignores it and closes the
period regardless.
*/

SELECT '=== TEST 4: FINANCIAL CLOSE ===' AS TestCase;

EXECUTE IMMEDIATE $$
DECLARE
    v_period_id INT;
    v_result VARIANT;
    v_is_closed BOOLEAN;
    v_unallocated INT;
    EX_NO_PERIOD EXCEPTION (-20930, 'TEST 4 failed: no fiscal period for January 2024');
    EX_NOT_CLOSED EXCEPTION (-20931, 'TEST 4 failed: period is not closed after close');
    EX_NOT_ALLOCATED EXCEPTION (-20932, 'TEST 4 failed: budget lines in the closed period are not marked allocated');
BEGIN
    v_period_id := (SELECT FiscalPeriodID FROM Planning.FiscalPeriod WHERE FiscalYear = 2024 AND FiscalMonth = 1);
    IF (v_period_id IS NULL) THEN
        RAISE EX_NO_PERIOD;
    END IF;

    CALL Planning.usp_PerformFinancialClose(:v_period_id, 'PERIOD', FALSE, FALSE) INTO :v_result;

    v_is_closed := (SELECT IsClosed FROM Planning.FiscalPeriod WHERE FiscalPeriodID = :v_period_id);
    IF (NOT COALESCE(v_is_closed, FALSE)) THEN
        RAISE EX_NOT_CLOSED;
    END IF;

    v_unallocated := (
        SELECT COUNT(*) FROM Planning.BudgetLineItem
        WHERE FiscalPeriodID = :v_period_id AND IsAllocated = FALSE
    );
    IF (v_unallocated <> 0) THEN
        RAISE EX_NOT_ALLOCATED;
    END IF;

    RETURN 'TEST 4 passed: period ' || v_period_id || ' closed';
END;
$$;

/*
================================================================================
TEST 5: usp_ProcessBudgetConsolidation
================================================================================

Exactly one new journal, its ID returned by the procedure, holding one line per
budget line on an active cost center.
*/

SELECT '=== TEST 5: BUDGET CONSOLIDATION ===' AS TestCase;

EXECUTE IMMEDIATE $$
DECLARE
    v_budget_id INT;
    v_result VARIANT;
    v_journal_id INT;
    v_journals_before INT;
    v_journals_after INT;
    v_expected_lines INT;
    v_actual_lines INT;
    v_reported_lines INT;
    EX_NO_JOURNAL EXCEPTION (-20941, 'TEST 5 failed: procedure did not return the journal it created');
    EX_JOURNAL_COUNT EXCEPTION (-20942, 'TEST 5 failed: expected exactly one new consolidation journal');
    EX_LINE_COUNT EXCEPTION (-20943, 'TEST 5 failed: journal lines do not match the active-cost-center budget lines');
BEGIN
    v_budget_id := (SELECT BudgetHeaderID FROM Planning.BudgetHeader WHERE BudgetCode = 'BUDGET-2024-001');
    v_journals_before := (
        SELECT COUNT(*) FROM Planning.ConsolidationJournal
        WHERE BudgetHeaderID = :v_budget_id AND JournalType = 'CONSOLIDATION'
    );

    CALL Planning.usp_ProcessBudgetConsolidation(:v_budget_id, 'FULL', TRUE) INTO :v_result;

    v_journal_id := (SELECT :v_result:journal_id::INT);
    IF (v_journal_id IS NULL) THEN
        RAISE EX_NO_JOURNAL;
    END IF;

    v_journals_after := (
        SELECT COUNT(*) FROM Planning.ConsolidationJournal
        WHERE BudgetHeaderID = :v_budget_id AND JournalType = 'CONSOLIDATION'
    );
    IF (v_journals_after <> v_journals_before + 1) THEN
        RAISE EX_JOURNAL_COUNT;
    END IF;

    v_expected_lines := (
        SELECT COUNT(*)
        FROM Planning.BudgetLineItem bli
        JOIN Planning.CostCenter cc ON bli.CostCenterID = cc.CostCenterID AND cc.IsActive = TRUE
        WHERE bli.BudgetHeaderID = :v_budget_id
    );
    v_actual_lines := (SELECT COUNT(*) FROM Planning.ConsolidationJournalLine WHERE JournalID = :v_journal_id);
    v_reported_lines := (SELECT :v_result:consolidated_lines::INT);
    IF (v_actual_lines <> v_expected_lines OR v_reported_lines <> v_actual_lines) THEN
        RAISE EX_LINE_COUNT;
    END IF;

    RETURN 'TEST 5 passed: one journal, ' || v_actual_lines || ' lines';
END;
$$;

/*
================================================================================
TEST 6: usp_ReconcileIntercompanyBalances
================================================================================

The procedure does not match or eliminate yet; it counts the intercompany lines
in the period. This pins that count.
*/

SELECT '=== TEST 6: INTERCOMPANY RECONCILIATION ===' AS TestCase;

EXECUTE IMMEDIATE $$
DECLARE
    v_period_id INT;
    v_result VARIANT;
    v_expected INT;
    v_reported INT;
    EX_COUNT EXCEPTION (-20951, 'TEST 6 failed: reconciled_count does not match the intercompany lines in the period');
BEGIN
    v_period_id := (SELECT FiscalPeriodID FROM Planning.FiscalPeriod WHERE FiscalYear = 2024 AND FiscalMonth = 1);

    CALL Planning.usp_ReconcileIntercompanyBalances(:v_period_id, 0.01, 2024, FALSE) INTO :v_result;

    v_expected := (
        SELECT COUNT(*)
        FROM Planning.BudgetLineItem bli
        JOIN Planning.GLAccount ga ON bli.GLAccountID = ga.GLAccountID
        WHERE ga.IntercompanyFlag = TRUE
        AND bli.FiscalPeriodID = :v_period_id
    );
    v_reported := (SELECT :v_result:reconciled_count::INT);
    IF (v_reported IS NULL OR v_reported <> v_expected) THEN
        RAISE EX_COUNT;
    END IF;

    RETURN 'TEST 6 passed: ' || v_reported || ' intercompany lines';
END;
$$;

/*
================================================================================
SUMMARY
================================================================================

Reaching this point means every assertion above held: a failing test raises
and halts the run. The queries below are informational only.
*/

SELECT '=== ALL PROCEDURE TESTS PASSED ===' AS FinalStatus;

-- Final data summary
SELECT
    'FINAL DATA SUMMARY' AS Category,
    'Fiscal Periods' AS Item,
    COUNT(*)::VARCHAR AS Value
FROM Planning.FiscalPeriod
UNION ALL
SELECT 'FINAL DATA SUMMARY', 'GL Accounts', COUNT(*)::VARCHAR FROM Planning.GLAccount
UNION ALL
SELECT 'FINAL DATA SUMMARY', 'Cost Centers', COUNT(*)::VARCHAR FROM Planning.CostCenter
UNION ALL
SELECT 'FINAL DATA SUMMARY', 'Allocation Rules', COUNT(*)::VARCHAR FROM Planning.AllocationRule
UNION ALL
SELECT 'FINAL DATA SUMMARY', 'Budget Headers', COUNT(*)::VARCHAR FROM Planning.BudgetHeader
UNION ALL
SELECT 'FINAL DATA SUMMARY', 'Budget Line Items', COUNT(*)::VARCHAR FROM Planning.BudgetLineItem
UNION ALL
SELECT 'FINAL DATA SUMMARY', 'Consolidation Journals', COUNT(*)::VARCHAR FROM Planning.ConsolidationJournal
UNION ALL
SELECT 'FINAL DATA SUMMARY', 'Consolidation Lines', COUNT(*)::VARCHAR FROM Planning.ConsolidationJournalLine
ORDER BY Category, Item;

-- Show comprehensive budget analysis
SELECT
    'BUDGET ANALYSIS WITH TESTSAMPLE DATA' AS ResultType,
    bh.BudgetCode,
    bh.BudgetName,
    COUNT(DISTINCT bli.FiscalPeriodID) AS PeriodsIncluded,
    COUNT(*) AS LineItemCount,
    SUM(bli.OriginalAmount) AS TotalOriginal,
    SUM(bli.AdjustedAmount) AS TotalAdjusted,
    SUM(bli.FinalAmount) AS TotalFinal,
    ROUND(SUM(bli.FinalAmount) / NULLIF(SUM(bli.OriginalAmount), 0), 4) AS FinalToOriginalRatio
FROM Planning.BudgetLineItem bli
JOIN Planning.BudgetHeader bh ON bli.BudgetHeaderID = bh.BudgetHeaderID
WHERE bh.BudgetCode = 'BUDGET-2024-001'
GROUP BY bh.BudgetCode, bh.BudgetName
ORDER BY bh.BudgetCode;

-- Show cost center allocation summary
SELECT
    'COST CENTER HIERARCHY SUMMARY' AS Summary,
    cc.CostCenterCode,
    cc.CostCenterName,
    COALESCE(parent.CostCenterCode, 'ROOT') AS ParentCode,
    COUNT(DISTINCT bli.BudgetLineItemID) AS BudgetLineCount,
    SUM(bli.FinalAmount) AS TotalBudgetAmount
FROM Planning.CostCenter cc
LEFT JOIN Planning.CostCenter parent ON cc.ParentCostCenterID = parent.CostCenterID
LEFT JOIN Planning.BudgetLineItem bli ON cc.CostCenterID = bli.CostCenterID
WHERE cc.IsActive = TRUE
GROUP BY cc.CostCenterCode, cc.CostCenterName, parent.CostCenterCode
ORDER BY cc.CostCenterCode;

-- Show GL Account distribution
SELECT
    'GL ACCOUNT DISTRIBUTION' AS Summary,
    CASE
        WHEN ga.AccountType = 'R' THEN 'Revenue'
        WHEN ga.AccountType = 'X' THEN 'Expense'
        WHEN ga.AccountType = 'A' THEN 'Asset'
        WHEN ga.AccountType = 'L' THEN 'Liability'
        WHEN ga.AccountType = 'E' THEN 'Equity'
    END AS AccountCategory,
    COUNT(*) AS AccountCount,
    SUM(CASE WHEN bli.FiscalPeriodID IS NOT NULL THEN 1 ELSE 0 END) AS BudgetedAccounts,
    SUM(COALESCE(bli.FinalAmount, 0)) AS TotalBudgetAmount
FROM Planning.GLAccount ga
LEFT JOIN Planning.BudgetHeader bh ON bh.BudgetCode = 'BUDGET-2024-001'
LEFT JOIN Planning.BudgetLineItem bli ON ga.GLAccountID = bli.GLAccountID AND bli.BudgetHeaderID = bh.BudgetHeaderID
WHERE ga.IsActive = TRUE
GROUP BY CASE
            WHEN ga.AccountType = 'R' THEN 'Revenue'
            WHEN ga.AccountType = 'X' THEN 'Expense'
            WHEN ga.AccountType = 'A' THEN 'Asset'
            WHEN ga.AccountType = 'L' THEN 'Liability'
            WHEN ga.AccountType = 'E' THEN 'Equity'
         END
ORDER BY AccountCategory;
