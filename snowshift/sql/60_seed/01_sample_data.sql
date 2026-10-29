/*
================================================================================
LOAD SAMPLE DATA
================================================================================

Financial Planning Schema - Sample Data Loading

This script loads test data into the schema created by sql/00_setup .. sql/50_procedures

EXECUTION TIME: 3-5 minutes
TOTAL RECORDS: 400+ rows

Prerequisite: Main.sql must be executed first

================================================================================
SECTION 1: FISCAL PERIOD DATA
================================================================================
*/

USE WAREHOUSE MIGRATION_WH;
USE DATABASE SNOWCONVERT_DEMO;
USE SCHEMA Planning;


-- Load Fiscal Period Data (15 records)
INSERT INTO Planning.FiscalPeriod (
    FiscalYear, FiscalQuarter, FiscalMonth, PeriodName, 
    PeriodStartDate, PeriodEndDate, IsClosed, IsAdjustmentPeriod, WorkingDays
)
VALUES
(2024, 1, 1, 'January 2024', '2024-01-01', '2024-01-31', FALSE, FALSE, 23),
(2024, 1, 2, 'February 2024', '2024-02-01', '2024-02-29', FALSE, FALSE, 21),
(2024, 1, 3, 'March 2024', '2024-03-01', '2024-03-31', FALSE, FALSE, 21),
(2024, 2, 4, 'April 2024', '2024-04-01', '2024-04-30', FALSE, FALSE, 22),
(2024, 2, 5, 'May 2024', '2024-05-01', '2024-05-31', FALSE, FALSE, 23),
(2024, 2, 6, 'June 2024', '2024-06-01', '2024-06-30', FALSE, FALSE, 21),
(2024, 3, 7, 'July 2024', '2024-07-01', '2024-07-31', FALSE, FALSE, 23),
(2024, 3, 8, 'August 2024', '2024-08-01', '2024-08-31', FALSE, FALSE, 22),
(2024, 3, 9, 'September 2024', '2024-09-01', '2024-09-30', FALSE, FALSE, 21),
(2024, 4, 10, 'October 2024', '2024-10-01', '2024-10-31', FALSE, FALSE, 23),
(2024, 4, 11, 'November 2024', '2024-11-01', '2024-11-30', FALSE, FALSE, 21),
(2024, 4, 12, 'December 2024', '2024-12-01', '2024-12-31', FALSE, FALSE, 23),
(2025, 1, 1, 'January 2025', '2025-01-01', '2025-01-31', FALSE, FALSE, 23),
(2025, 1, 2, 'February 2025', '2025-02-01', '2025-02-28', FALSE, FALSE, 20),
(2025, 1, 3, 'March 2025', '2025-03-01', '2025-03-31', FALSE, FALSE, 21);

SELECT COUNT(*) as FiscalPeriod_Records FROM Planning.FiscalPeriod;

/*
================================================================================
SECTION 2: GL ACCOUNT DATA

20 records
================================================================================
*/

INSERT INTO Planning.GLAccount (
    AccountNumber, AccountName, AccountType, AccountSubType, 
    IsPostable, IsBudgetable, IsStatistical, NormalBalance, 
    CurrencyCode, IntercompanyFlag, IsActive
)
VALUES
('4000', 'Product Revenue', 'R', 'Revenue', TRUE, TRUE, FALSE, 'C', 'USD', FALSE, TRUE),
('4100', 'Service Revenue', 'R', 'Revenue', TRUE, TRUE, FALSE, 'C', 'USD', FALSE, TRUE),
('4200', 'Consulting Revenue', 'R', 'Revenue', TRUE, TRUE, FALSE, 'C', 'USD', FALSE, TRUE),
('4300', 'Other Revenue', 'R', 'Revenue', TRUE, TRUE, FALSE, 'C', 'USD', FALSE, TRUE),
('4500', 'Intercompany Revenue', 'R', 'Revenue', TRUE, TRUE, FALSE, 'C', 'USD', TRUE, TRUE),
('5000', 'Salaries & Wages', 'X', 'Compensation', TRUE, TRUE, FALSE, 'D', 'USD', FALSE, TRUE),
('5100', 'Employee Benefits', 'X', 'Compensation', TRUE, TRUE, FALSE, 'D', 'USD', FALSE, TRUE),
('5200', 'Office Rent', 'X', 'Occupancy', TRUE, TRUE, FALSE, 'D', 'USD', FALSE, TRUE),
('5300', 'Utilities', 'X', 'Occupancy', TRUE, TRUE, FALSE, 'D', 'USD', FALSE, TRUE),
('5400', 'Depreciation', 'X', 'Depreciation', TRUE, TRUE, FALSE, 'D', 'USD', FALSE, TRUE),
('5500', 'Supplies', 'X', 'Supplies', TRUE, TRUE, FALSE, 'D', 'USD', FALSE, TRUE),
('5600', 'Travel', 'X', 'Travel', TRUE, TRUE, FALSE, 'D', 'USD', FALSE, TRUE),
('5700', 'Professional Services', 'X', 'Services', TRUE, TRUE, FALSE, 'D', 'USD', FALSE, TRUE),
('5900', 'Intercompany Expense', 'X', 'Intercompany', TRUE, TRUE, FALSE, 'D', 'USD', TRUE, TRUE),
('1000', 'Cash', 'A', 'Current Asset', TRUE, FALSE, FALSE, 'D', 'USD', FALSE, TRUE),
('1100', 'Accounts Receivable', 'A', 'Current Asset', TRUE, FALSE, FALSE, 'D', 'USD', FALSE, TRUE),
('1500', 'Fixed Assets', 'A', 'Fixed Asset', TRUE, FALSE, FALSE, 'D', 'USD', FALSE, TRUE),
('2000', 'Accounts Payable', 'L', 'Current Liability', TRUE, FALSE, FALSE, 'C', 'USD', FALSE, TRUE),
('2100', 'Accrued Expenses', 'L', 'Current Liability', TRUE, FALSE, FALSE, 'C', 'USD', FALSE, TRUE),
('3000', 'Retained Earnings', 'E', 'Equity', FALSE, FALSE, FALSE, 'C', 'USD', FALSE, TRUE);

SELECT COUNT(*) as GLAccount_Records FROM Planning.GLAccount;

/*
================================================================================
SECTION 3: COST CENTER DATA

11 records
================================================================================
*/

INSERT INTO Planning.CostCenter (
    CostCenterCode, CostCenterName, ParentCostCenterID, 
    ManagerEmployeeID, DepartmentCode, IsActive, 
    EffectiveFromDate, AllocationWeight
)
VALUES
('CORP', 'Corporate', NULL, 1, NULL, TRUE, '2024-01-01', 1.0000),
('OPS', 'Operations Division', 1, 2, 'OPS', TRUE, '2024-01-01', 1.0000),
('SALES', 'Sales Department', 2, 3, 'SAL', TRUE, '2024-01-01', 0.4000),
('SALES-N', 'Sales - North', 3, 4, 'SAL', TRUE, '2024-01-01', 0.2000),
('SALES-S', 'Sales - South', 3, 5, 'SAL', TRUE, '2024-01-01', 0.2000),
('OPS-DEPT', 'Operations Dept', 2, 6, 'OPS', TRUE, '2024-01-01', 0.3000),
('FIN', 'Finance Division', 1, 7, NULL, TRUE, '2024-01-01', 1.0000),
('ACC', 'Accounting', 7, 8, 'ACC', TRUE, '2024-01-01', 0.5000),
('FP', 'Financial Planning', 7, 9, 'FP', TRUE, '2024-01-01', 0.5000),
('HR', 'Human Resources', 1, 10, NULL, TRUE, '2024-01-01', 1.0000),
('IT', 'Information Technology', 1, 11, NULL, TRUE, '2024-01-01', 1.0000);

SELECT COUNT(*) as CostCenter_Records FROM Planning.CostCenter;

/*
================================================================================
SECTION 4: ALLOCATION RULE DATA
3 rows
================================================================================
*/

INSERT INTO Planning.AllocationRule (
    RuleCode, RuleName, RuleDescription, RuleType, AllocationMethod,
    SourceCostCenterID, TargetSpecification, AllocationBasis, AllocationPercentage,
    RoundingMethod, RoundingPrecision, ExecutionSequence,
    EffectiveFromDate, IsActive
)
SELECT 'CORP-ALLOC-1', 'Corporate Overhead Allocation', 'Allocate corporate overhead to operations and finance divisions',
    'DIRECT', 'HEADCOUNT', 1, PARSE_JSON('{"targetCostCenters": ["OPS", "FIN"]}'),
    'HEADCOUNT', NULL, 'NEAREST', 2, 10, '2024-01-01', TRUE
UNION ALL
SELECT 'FIN-ALLOC-2', 'Finance Department Allocation', 'Allocate finance department costs based on headcount',
    'STEP_DOWN', 'HEADCOUNT', 7, PARSE_JSON('{"targetCostCenters": ["ACC", "FP"]}'),
    'HEADCOUNT', NULL, 'NEAREST', 2, 20, '2024-01-01', TRUE
UNION ALL
SELECT 'OPS-ALLOC-3', 'Operations Cost Allocation', 'Allocate operations costs to departments',
    'DIRECT', 'REVENUE', 2, PARSE_JSON('{"targetCostCenters": ["SALES", "OPS-DEPT"]}'),
    'REVENUE', NULL, 'NEAREST', 2, 15, '2024-01-01', TRUE;

SELECT COUNT(*) as AllocationRule_Records FROM Planning.AllocationRule;

/*
================================================================================
SECTION 5: BUDGET HEADER DATA

3 rows
================================================================================
*/

INSERT INTO Planning.BudgetHeader (
    BudgetCode, BudgetName, BudgetType, ScenarioType, FiscalYear,
    StartPeriodID, EndPeriodID, StatusCode, VersionNumber, IsLocked
)
(SELECT
    'BUDGET-2024-001',
    '2024 Annual Budget - Base Case',
    'ANNUAL',
    'BASE',
    2024,
    MIN(CASE WHEN FiscalMonth = 1 THEN FiscalPeriodID END) OVER (),
    MAX(CASE WHEN FiscalMonth = 12 THEN FiscalPeriodID END) OVER (),
    'DRAFT',
    1,
    FALSE
FROM Planning.FiscalPeriod
WHERE FiscalYear = 2024
LIMIT 1)

UNION ALL

(SELECT
    'BUDGET-2024-002',
    '2024 Rolling Forecast - Optimistic',
    'ROLLING',
    'OPTIMISTIC',
    2024,
    MIN(CASE WHEN FiscalMonth = 2 THEN FiscalPeriodID END) OVER (),
    MAX(CASE WHEN FiscalMonth = 12 THEN FiscalPeriodID END) OVER (),
    'DRAFT',
    1,
    FALSE
FROM Planning.FiscalPeriod
WHERE FiscalYear = 2024
LIMIT 1)

UNION ALL

(SELECT
    'BUDGET-2024-003',
    '2024 Rolling Forecast - Conservative',
    'ROLLING',
    'PESSIMISTIC',
    2024,
    MIN(CASE WHEN FiscalMonth = 3 THEN FiscalPeriodID END) OVER (),
    MAX(CASE WHEN FiscalMonth = 12 THEN FiscalPeriodID END) OVER (),
    'DRAFT',
    1,
    FALSE
FROM Planning.FiscalPeriod
WHERE FiscalYear = 2024
LIMIT 1);

SELECT COUNT(*) as BudgetHeader_Records FROM Planning.BudgetHeader;

/*
================================================================================
SECTION 6: BUDGET LINE ITEM DATA

250 rows
================================================================================
*/

INSERT INTO Planning.BudgetLineItem (
    BudgetHeaderID, GLAccountID, CostCenterID, FiscalPeriodID,
    OriginalAmount, AdjustedAmount, FinalAmount, 
    SpreadMethodCode, IsAllocated
)
WITH budget_combos AS (
    SELECT 
        bh.BudgetHeaderID,
        ga.GLAccountID,
        cc.CostCenterID,
        fp.FiscalPeriodID,
        CASE 
            WHEN ga.AccountType = 'R' THEN ROUND(UNIFORM(100000::FLOAT, 600000::FLOAT, RANDOM()), 2)
            WHEN ga.AccountType = 'X' THEN ROUND(UNIFORM(10000::FLOAT, 60000::FLOAT, RANDOM()), 2)
            ELSE ROUND(UNIFORM(0::FLOAT, 100000::FLOAT, RANDOM()), 2)
        END AS base_amount
    FROM Planning.BudgetHeader bh
    CROSS JOIN Planning.GLAccount ga
    CROSS JOIN Planning.CostCenter cc
    CROSS JOIN Planning.FiscalPeriod fp
    WHERE bh.BudgetCode = 'BUDGET-2024-001'
    AND ga.IsBudgetable = TRUE
    AND cc.IsActive = TRUE
    AND fp.FiscalYear = 2024
)
SELECT 
    BudgetHeaderID,
    GLAccountID,
    CostCenterID,
    FiscalPeriodID,
    base_amount,
    ROUND(base_amount * UNIFORM(0::FLOAT, 0.1::FLOAT, RANDOM()), 2),
    base_amount + ROUND(base_amount * UNIFORM(0::FLOAT, 0.1::FLOAT, RANDOM()), 2),
    'EVEN',
    FALSE
FROM budget_combos
WHERE UNIFORM(0::FLOAT, 1::FLOAT, RANDOM()) > 0.7
LIMIT 250;

SELECT COUNT(*) as BudgetLineItem_Records FROM Planning.BudgetLineItem;

/*
================================================================================
SECTION 7: CONSOLIDATION JOURNAL DATA

5 rows
================================================================================
*/

INSERT INTO Planning.ConsolidationJournal (
    JournalNumber, JournalType, BudgetHeaderID, FiscalPeriodID,
    PostingDate, Description, StatusCode, IsBalanced
)
SELECT
    'CONS-2024-' || ROW_NUMBER() OVER (ORDER BY bh.BudgetHeaderID),
    'ELIMINATION',
    bh.BudgetHeaderID,
    fp.FiscalPeriodID,
    fp.PeriodEndDate,
    'Consolidation adjustments for ' || fp.PeriodName,
    'DRAFT',
    FALSE
FROM Planning.BudgetHeader bh
CROSS JOIN Planning.FiscalPeriod fp
WHERE bh.BudgetCode = 'BUDGET-2024-001'
AND fp.FiscalYear = 2024
AND fp.FiscalMonth IN (1, 3, 6, 9, 12);

SELECT COUNT(*) as ConsolidationJournal_Records FROM Planning.ConsolidationJournal;

/*
================================================================================
SECTION 8: CONSOLIDATION JOURNAL LINE DATA

100 rows
================================================================================
*/

INSERT INTO Planning.ConsolidationJournalLine (
    JournalID, LineNumber, GLAccountID, CostCenterID,
    DebitAmount, CreditAmount, NetAmount, Description
)
SELECT
    cj.JournalID,
    ROW_NUMBER() OVER (PARTITION BY cj.JournalID ORDER BY ga.GLAccountID),
    ga.GLAccountID,
    cc.CostCenterID,
    CASE WHEN ga.NormalBalance = 'D' THEN ROUND(UNIFORM(1000::FLOAT, 11000::FLOAT, RANDOM()), 2) ELSE 0 END,
    CASE WHEN ga.NormalBalance = 'C' THEN ROUND(UNIFORM(1000::FLOAT, 11000::FLOAT, RANDOM()), 2) ELSE 0 END,
    CASE WHEN ga.NormalBalance = 'D' THEN ROUND(UNIFORM(1000::FLOAT, 11000::FLOAT, RANDOM()), 2) 
         ELSE -ROUND(UNIFORM(1000::FLOAT, 11000::FLOAT, RANDOM()), 2) END,
    'Consolidation: ' || ga.AccountName || ' - ' || cc.CostCenterName
FROM Planning.ConsolidationJournal cj
CROSS JOIN Planning.GLAccount ga
CROSS JOIN Planning.CostCenter cc
WHERE ga.IsPostable = TRUE
AND cc.IsActive = TRUE
AND UNIFORM(0::FLOAT, 1::FLOAT, RANDOM()) > 0.8
LIMIT 100;

SELECT COUNT(*) as ConsolidationJournalLine_Records FROM Planning.ConsolidationJournalLine;

/*
================================================================================
FINAL VERIFICATION
================================================================================
*/

SELECT '=== DATA LOADING COMPLETE ===' AS Status;

SELECT 
    'FiscalPeriod' AS TableName,
    COUNT(*) AS RecordCount
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
ORDER BY TableName;

-- Show sample budget data
SELECT
    bh.BudgetCode,
    bh.BudgetName,
    ga.AccountNumber,
    ga.AccountName,
    cc.CostCenterCode,
    cc.CostCenterName,
    bli.OriginalAmount,
    bli.AdjustedAmount,
    bli.FinalAmount
FROM Planning.BudgetLineItem bli
JOIN Planning.BudgetHeader bh ON bli.BudgetHeaderID = bh.BudgetHeaderID
JOIN Planning.GLAccount ga ON bli.GLAccountID = ga.GLAccountID
JOIN Planning.CostCenter cc ON bli.CostCenterID = cc.CostCenterID
ORDER BY bli.BudgetLineItemID
LIMIT 10;

SELECT '=== SAMPLE DATA LOADING COMPLETE ===' AS CompletionStatus;

