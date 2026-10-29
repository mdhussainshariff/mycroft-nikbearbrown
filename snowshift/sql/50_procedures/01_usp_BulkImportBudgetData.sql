-- PROCEDURE 1: Bulk Import Budget Data
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.
--
-- The payload carries natural keys (account number, cost center code, fiscal
-- year/month); they are resolved to surrogate IDs here. Duplicate keys are
-- handled explicitly because the natural-key UNIQUE constraint on
-- BudgetLineItem is declared but not enforced -- without these checks a
-- re-run would silently double the budget.

CREATE OR REPLACE PROCEDURE SNOWCONVERT_DEMO.PLANNING.USP_BULKIMPORTBUDGETDATA("IMPORT_SOURCE" VARCHAR, "TARGET_BUDGET_HEADER_ID" NUMBER(38,0), "FILE_PATH" VARCHAR DEFAULT null, "BUDGET_DATA" VARIANT DEFAULT null, "STAGING_TABLE_NAME" VARCHAR DEFAULT null, "VALIDATION_MODE" VARCHAR DEFAULT 'STRICT', "DUPLICATE_HANDLING" VARCHAR DEFAULT 'REJECT', "BATCH_SIZE" NUMBER(38,0) DEFAULT 10000, "USE_PARALLEL_LOAD" BOOLEAN DEFAULT TRUE)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    v_start_time TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    v_import_batch_id VARCHAR(36) := UUID_STRING();
    v_total_rows INT := 0;
    v_inserted_rows INT := 0;
    v_updated_rows INT := 0;
    v_imported_rows INT := 0;
    v_invalid_rows INT := 0;
    v_rejections ARRAY;
    v_result_json VARIANT;
    EX_INVALID_DUPLICATE_HANDLING EXCEPTION (-20004, 'Duplicate handling must be REJECT or UPDATE');
BEGIN
    IF (COALESCE(duplicate_handling, '') NOT IN ('REJECT', 'UPDATE')) THEN
        RAISE EX_INVALID_DUPLICATE_HANDLING;
    END IF;

    -- OR REPLACE: a call that failed part-way leaves this table behind for
    -- the rest of the session.
    CREATE OR REPLACE TEMPORARY TABLE temp_import_staging (
        row_id INT AUTOINCREMENT PRIMARY KEY,
        gl_account_id INT,
        account_number VARCHAR(20),
        cost_center_id INT,
        cost_center_code VARCHAR(20),
        fiscal_period_id INT,
        fiscal_year SMALLINT,
        fiscal_month TINYINT,
        original_amount DECIMAL(19,4),
        adjusted_amount DECIMAL(19,4),
        spread_method_code VARCHAR(10),
        notes VARCHAR(500),
        is_valid BOOLEAN DEFAULT TRUE,
        validation_errors VARCHAR(4000),
        line_exists BOOLEAN DEFAULT FALSE,
        is_processed BOOLEAN DEFAULT FALSE
    );

    IF (import_source = 'VARIANT') THEN
        INSERT INTO temp_import_staging (
            account_number, cost_center_code, fiscal_year, fiscal_month,
            original_amount, adjusted_amount, spread_method_code, notes
        )
        SELECT
            value:account_number::VARCHAR,
            value:cost_center_code::VARCHAR,
            value:fiscal_year::SMALLINT,
            value:fiscal_month::TINYINT,
            value:original_amount::DECIMAL(19,4),
            value:adjusted_amount::DECIMAL(19,4),
            value:spread_method_code::VARCHAR,
            value:notes::VARCHAR
        FROM TABLE(FLATTEN(INPUT => :budget_data));

        v_total_rows := (SELECT COUNT(*) FROM temp_import_staging);
    END IF;

    -- Resolve natural keys to surrogate IDs. A code matching more than one
    -- row is left unresolved rather than guessed at: the UNIQUE constraints on
    -- these lookup tables are not enforced either.
    UPDATE temp_import_staging tis
    SET gl_account_id = ga.GLAccountID
    FROM (
        SELECT AccountNumber, MIN(GLAccountID) AS GLAccountID
        FROM Planning.GLAccount
        GROUP BY AccountNumber
        HAVING COUNT(*) = 1
    ) ga
    WHERE tis.account_number = ga.AccountNumber;

    UPDATE temp_import_staging tis
    SET cost_center_id = cc.CostCenterID
    FROM (
        SELECT CostCenterCode, MIN(CostCenterID) AS CostCenterID
        FROM Planning.CostCenter
        GROUP BY CostCenterCode
        HAVING COUNT(*) = 1
    ) cc
    WHERE tis.cost_center_code = cc.CostCenterCode;

    UPDATE temp_import_staging tis
    SET fiscal_period_id = fp.FiscalPeriodID
    FROM (
        SELECT FiscalYear, FiscalMonth, MIN(FiscalPeriodID) AS FiscalPeriodID
        FROM Planning.FiscalPeriod
        GROUP BY FiscalYear, FiscalMonth
        HAVING COUNT(*) = 1
    ) fp
    WHERE tis.fiscal_year = fp.FiscalYear
    AND tis.fiscal_month = fp.FiscalMonth;

    -- Unkeyed rows are rejected in every validation mode: the target columns
    -- are NOT NULL, so there is nothing to relax.
    UPDATE temp_import_staging
    SET is_valid = FALSE,
        validation_errors = CASE
            WHEN gl_account_id IS NULL THEN 'Unknown or ambiguous account_number'
            WHEN cost_center_id IS NULL THEN 'Unknown or ambiguous cost_center_code'
            ELSE 'No unique fiscal period for fiscal_year/fiscal_month'
        END
    WHERE gl_account_id IS NULL
    OR cost_center_id IS NULL
    OR fiscal_period_id IS NULL;

    IF (validation_mode IN ('STRICT', 'LENIENT')) THEN
        UPDATE temp_import_staging
        SET is_valid = FALSE,
            validation_errors = 'Missing required fields'
        WHERE is_valid
        AND original_amount IS NULL;
    END IF;

    -- The same key twice in one payload has no right answer for which amount
    -- wins, so every copy is rejected. SQL Server's unique key failed the
    -- statement here; Snowflake would have inserted all of them.
    UPDATE temp_import_staging tis
    SET is_valid = FALSE,
        validation_errors = 'Duplicate key within the import payload'
    FROM (
        SELECT gl_account_id, cost_center_id, fiscal_period_id
        FROM temp_import_staging
        WHERE gl_account_id IS NOT NULL
        AND cost_center_id IS NOT NULL
        AND fiscal_period_id IS NOT NULL
        GROUP BY gl_account_id, cost_center_id, fiscal_period_id
        HAVING COUNT(*) > 1
    ) dup
    WHERE tis.is_valid
    AND tis.gl_account_id = dup.gl_account_id
    AND tis.cost_center_id = dup.cost_center_id
    AND tis.fiscal_period_id = dup.fiscal_period_id;

    UPDATE temp_import_staging tis
    SET line_exists = TRUE
    FROM (
        SELECT DISTINCT GLAccountID, CostCenterID, FiscalPeriodID
        FROM Planning.BudgetLineItem
        WHERE BudgetHeaderID = :target_budget_header_id
    ) bli
    WHERE tis.is_valid
    AND tis.gl_account_id = bli.GLAccountID
    AND tis.cost_center_id = bli.CostCenterID
    AND tis.fiscal_period_id = bli.FiscalPeriodID;

    IF (duplicate_handling = 'REJECT') THEN
        UPDATE temp_import_staging
        SET is_valid = FALSE,
            validation_errors = 'Line already exists in the target budget'
        WHERE is_valid
        AND line_exists;
    END IF;

    BEGIN TRANSACTION;

    IF (duplicate_handling = 'UPDATE') THEN
        -- Staging keys are unique among valid rows, so each target line
        -- matches at most one source row and the update is deterministic.
        UPDATE Planning.BudgetLineItem bli
        SET OriginalAmount = tis.original_amount,
            AdjustedAmount = COALESCE(tis.adjusted_amount, 0),
            FinalAmount = tis.original_amount + COALESCE(tis.adjusted_amount, 0),
            SpreadMethodCode = COALESCE(tis.spread_method_code, bli.SpreadMethodCode),
            ImportBatchID = :v_import_batch_id,
            LastModifiedDateTime = CURRENT_TIMESTAMP()
        FROM temp_import_staging tis
        WHERE tis.is_valid
        AND tis.line_exists
        AND bli.BudgetHeaderID = :target_budget_header_id
        AND bli.GLAccountID = tis.gl_account_id
        AND bli.CostCenterID = tis.cost_center_id
        AND bli.FiscalPeriodID = tis.fiscal_period_id;

        v_updated_rows := (SELECT COUNT(*) FROM temp_import_staging WHERE is_valid AND line_exists);
    END IF;

    INSERT INTO Planning.BudgetLineItem (
        BudgetHeaderID, GLAccountID, CostCenterID, FiscalPeriodID,
        OriginalAmount, AdjustedAmount, FinalAmount, SpreadMethodCode,
        ImportBatchID, LastModifiedDateTime
    )
    SELECT
        :target_budget_header_id,
        tis.gl_account_id,
        tis.cost_center_id,
        tis.fiscal_period_id,
        tis.original_amount,
        COALESCE(tis.adjusted_amount, 0),
        tis.original_amount + COALESCE(tis.adjusted_amount, 0),
        tis.spread_method_code,
        :v_import_batch_id,
        CURRENT_TIMESTAMP()
    FROM temp_import_staging tis
    WHERE tis.is_valid
    AND NOT tis.line_exists;

    v_inserted_rows := SQLROWCOUNT;

    COMMIT;

    v_imported_rows := v_inserted_rows + v_updated_rows;
    v_invalid_rows := v_total_rows - v_imported_rows;

    v_rejections := (
        SELECT ARRAY_AGG(OBJECT_CONSTRUCT(
                   'row', row_id,
                   'account_number', account_number,
                   'cost_center_code', cost_center_code,
                   'error', validation_errors
               )) WITHIN GROUP (ORDER BY row_id)
        FROM (
            SELECT * FROM temp_import_staging
            WHERE NOT is_valid
            ORDER BY row_id
            LIMIT 100
        )
    );

    v_result_json := OBJECT_CONSTRUCT(
        'import_batch_id', v_import_batch_id,
        'import_source', :import_source,
        'duplicate_handling', :duplicate_handling,
        'total_rows_loaded', v_total_rows,
        'rows_imported', v_imported_rows,
        'rows_inserted', v_inserted_rows,
        'rows_updated', v_updated_rows,
        'rows_rejected', v_invalid_rows,
        'rejections', v_rejections,
        'status', CASE
            WHEN v_invalid_rows = 0 THEN 'SUCCESS'
            WHEN v_imported_rows = 0 THEN 'FAILED'
            ELSE 'PARTIAL_SUCCESS'
        END
    );

    DROP TABLE IF EXISTS temp_import_staging;

    RETURN v_result_json;
EXCEPTION
    WHEN OTHER THEN
        ROLLBACK;
        DROP TABLE IF EXISTS temp_import_staging;
        RAISE;
END;
$$;
