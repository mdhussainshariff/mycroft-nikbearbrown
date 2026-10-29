-- PROCEDURE 2: Execute Cost Allocation
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.
--
-- Snowflake has no SCOPE_IDENTITY(), and MAX(JournalID) is not this run's
-- journal once two runs overlap or the AUTOINCREMENT sequence is NOORDER. The
-- journal instead gets a number unique to this run and is read back by it. The
-- random suffix also keeps two runs in the same second apart, which SQL Server
-- guaranteed through UQ_ConsolidationJournal_Number and Snowflake does not.

CREATE OR REPLACE PROCEDURE SNOWCONVERT_DEMO.PLANNING.USP_EXECUTECOSTALLOCATION("BUDGET_HEADER_ID" NUMBER(38,0), "ALLOCATION_BASIS_OVERRIDE" VARCHAR DEFAULT null, "DRY_RUN" BOOLEAN DEFAULT FALSE, "INCLUDE_ZERO_AMOUNTS" BOOLEAN DEFAULT FALSE)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    v_start_time TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    v_total_allocated DECIMAL(19,4) := 0;
    v_rules_processed INT := 0;
    v_error_count INT := 0;
    v_result_json VARIANT;
    v_journal_id NUMBER;
    v_journal_number VARCHAR(30);
    EX_BUDGET_HEADER_REQUIRED EXCEPTION (-20001, 'Budget header ID is required');
    EX_BUDGET_HEADER_NOT_FOUND EXCEPTION (-20005, 'Budget header not found');
BEGIN
    IF (budget_header_id IS NULL) THEN
        RAISE EX_BUDGET_HEADER_REQUIRED;
    END IF;

    -- OR REPLACE: IF NOT EXISTS kept a previous call's rules for the session.
    CREATE OR REPLACE TEMPORARY TABLE temp_allocation_rules AS
    SELECT
        ar.AllocationRuleID,
        ar.RuleCode,
        ar.RuleName,
        ar.ExecutionSequence,
        ar.AllocationBasis,
        0 AS is_processed
    FROM Planning.AllocationRule ar
    WHERE ar.IsActive = TRUE
    ORDER BY ar.ExecutionSequence;

    v_rules_processed := (SELECT COUNT(*) FROM temp_allocation_rules);

    IF (:dry_run = FALSE) THEN
        v_journal_number := 'ALLOC-' || TO_CHAR(CURRENT_TIMESTAMP(), 'YYYYMMDDHH24MISS')
            || '-' || LEFT(UUID_STRING(), 8);

        BEGIN TRANSACTION;

        INSERT INTO Planning.ConsolidationJournal (
            JournalNumber,
            JournalType,
            BudgetHeaderID,
            FiscalPeriodID,
            PostingDate,
            Description,
            StatusCode
        )
        SELECT
            :v_journal_number,
            'ALLOCATION',
            :budget_header_id,
            bh.StartPeriodID,
            CURRENT_DATE(),
            'Cost allocation for budget ' || bh.BudgetCode,
            'DRAFT'
        FROM Planning.BudgetHeader bh
        WHERE bh.BudgetHeaderID = :budget_header_id;

        v_journal_id := (SELECT JournalID FROM Planning.ConsolidationJournal WHERE JournalNumber = :v_journal_number);

        IF (v_journal_id IS NULL) THEN
            RAISE EX_BUDGET_HEADER_NOT_FOUND;
        END IF;

        INSERT INTO Planning.ConsolidationJournalLine (
            JournalID,
            LineNumber,
            GLAccountID,
            CostCenterID,
            DebitAmount,
            CreditAmount,
            NetAmount,
            CreatedDateTime
        )
        SELECT
            :v_journal_id,
            ROW_NUMBER() OVER (ORDER BY bli.BudgetLineItemID),
            bli.GLAccountID,
            bli.CostCenterID,
            bli.FinalAmount,
            0,
            bli.FinalAmount,
            CURRENT_TIMESTAMP()
        FROM Planning.BudgetLineItem bli
        WHERE bli.BudgetHeaderID = :budget_header_id;

        v_total_allocated := (SELECT COALESCE(SUM(FinalAmount), 0) FROM Planning.BudgetLineItem WHERE BudgetHeaderID = :budget_header_id);

        COMMIT;
    END IF;

    v_result_json := OBJECT_CONSTRUCT(
        'allocation_start', v_start_time,
        'allocation_end', CURRENT_TIMESTAMP(),
        'rules_processed', v_rules_processed,
        'total_allocated', v_total_allocated,
        'error_count', v_error_count,
        'dry_run', :dry_run,
        'journal_id', v_journal_id,
        'journal_number', v_journal_number,
        'allocation_basis_override', :allocation_basis_override,
        'status', 'SUCCESS'
    );

    RETURN v_result_json;
EXCEPTION
    WHEN OTHER THEN
        ROLLBACK;
        RAISE;
END;
$$;
