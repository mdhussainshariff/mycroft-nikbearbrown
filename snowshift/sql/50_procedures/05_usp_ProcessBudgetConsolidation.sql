-- PROCEDURE 5: Process Budget Consolidation
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.
--
-- Snowflake has no SCOPE_IDENTITY(), and MAX(JournalID) is not this run's
-- journal once two runs overlap or the AUTOINCREMENT sequence is NOORDER. The
-- journal instead gets a number unique to this run and is read back by it. The
-- random suffix also keeps two runs in the same second apart, which SQL Server
-- guaranteed through UQ_ConsolidationJournal_Number and Snowflake does not.

CREATE OR REPLACE PROCEDURE SNOWCONVERT_DEMO.PLANNING.USP_PROCESSBUDGETCONSOLIDATION("BUDGET_HEADER_ID" NUMBER(38,0), "CONSOLIDATION_TYPE" VARCHAR DEFAULT 'FULL', "ELIMINATE_INTERCOMPANY" BOOLEAN DEFAULT TRUE)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    v_start_time TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    v_consolidated_lines INT := 0;
    v_eliminated_amount DECIMAL(19,4) := 0;
    v_result_json VARIANT;
    v_journal_id NUMBER;
    v_journal_number VARCHAR(30);
    EX_BUDGET_HEADER_REQUIRED EXCEPTION (-20001, 'Budget header ID is required');
    EX_BUDGET_HEADER_NOT_FOUND EXCEPTION (-20005, 'Budget header not found');
BEGIN
    IF (budget_header_id IS NULL) THEN
        RAISE EX_BUDGET_HEADER_REQUIRED;
    END IF;

    v_journal_number := 'CONSOL-' || TO_CHAR(CURRENT_TIMESTAMP(), 'YYYYMMDDHH24MISS')
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
        'CONSOLIDATION',
        :budget_header_id,
        bh.StartPeriodID,
        CURRENT_DATE(),
        'Budget consolidation (' || :consolidation_type || ') for budget ' || bh.BudgetCode,
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
    INNER JOIN Planning.CostCenter cc ON bli.CostCenterID = cc.CostCenterID AND cc.IsActive = TRUE
    WHERE bli.BudgetHeaderID = :budget_header_id;

    v_consolidated_lines := (SELECT COUNT(*) FROM Planning.ConsolidationJournalLine WHERE JournalID = :v_journal_id);

    COMMIT;

    v_result_json := OBJECT_CONSTRUCT(
        'consolidation_start', v_start_time,
        'consolidation_end', CURRENT_TIMESTAMP(),
        'budget_header_id', :budget_header_id,
        'consolidation_type', :consolidation_type,
        'eliminate_intercompany', :eliminate_intercompany,
        'consolidated_lines', v_consolidated_lines,
        'journal_id', v_journal_id,
        'journal_number', v_journal_number,
        'eliminated_amount', v_eliminated_amount,
        'status', 'SUCCESS'
    );

    RETURN v_result_json;
EXCEPTION
    WHEN OTHER THEN
        ROLLBACK;
        RAISE;
END;
$$;
