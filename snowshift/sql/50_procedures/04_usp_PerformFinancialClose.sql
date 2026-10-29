-- PROCEDURE 4: Perform Financial Close
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE PROCEDURE Planning.usp_PerformFinancialClose(
    fiscal_period_id INT,
    close_level VARCHAR DEFAULT 'PERIOD',
    validate_only BOOLEAN DEFAULT FALSE,
    include_consolidations BOOLEAN DEFAULT FALSE
)
RETURNS VARIANT
LANGUAGE SQL
AS
$$
DECLARE
    v_start_time TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    v_result_json VARIANT;
    EX_FISCAL_PERIOD_REQUIRED EXCEPTION (-20003, 'Fiscal period ID is required');
BEGIN
    IF (fiscal_period_id IS NULL) THEN
        RAISE EX_FISCAL_PERIOD_REQUIRED;
    END IF;
    
    UPDATE Planning.FiscalPeriod
    SET IsClosed = TRUE,
        ClosedDateTime = CURRENT_TIMESTAMP()
    WHERE FiscalPeriodID = :fiscal_period_id;
    
    UPDATE Planning.BudgetLineItem
    SET IsAllocated = TRUE
    WHERE FiscalPeriodID = :fiscal_period_id;
    
    v_result_json := OBJECT_CONSTRUCT(
        'status', 'SUCCESS',
        'close_start', v_start_time,
        'close_end', CURRENT_TIMESTAMP(),
        'period_id', :fiscal_period_id,
        'close_level', :close_level,
        'validation_errors', NULL
    );
    
    RETURN v_result_json;
END;
$$;
