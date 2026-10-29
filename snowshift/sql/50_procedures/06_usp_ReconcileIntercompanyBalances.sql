-- PROCEDURE 6: Reconcile Intercompany Balances
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE PROCEDURE Planning.usp_ReconcileIntercompanyBalances(
    fiscal_period_id INT,
    tolerance_amount DECIMAL DEFAULT 0.01,
    fiscal_year SMALLINT DEFAULT NULL,
    auto_eliminate_matched BOOLEAN DEFAULT FALSE
)
RETURNS VARIANT
LANGUAGE SQL
AS
$$
DECLARE
    v_start_time TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    v_reconciled INT := 0;
    v_variances INT := 0;
    v_variance_total DECIMAL(19,4) := 0;
    v_result_json VARIANT;
    EX_FISCAL_PERIOD_REQUIRED EXCEPTION (-20003, 'Fiscal period ID is required');
BEGIN
    IF (fiscal_period_id IS NULL) THEN
        RAISE EX_FISCAL_PERIOD_REQUIRED;
    END IF;
    
    CREATE TEMPORARY TABLE temp_intercompany_items AS
    SELECT 
        bli.BudgetLineItemID,
        cc.CostCenterID,
        bli.GLAccountID,
        bli.FiscalPeriodID,
        bli.FinalAmount,
        'UNMATCHED'::VARCHAR AS status
    FROM Planning.BudgetLineItem bli
    INNER JOIN Planning.GLAccount gla ON bli.GLAccountID = gla.GLAccountID
    INNER JOIN Planning.CostCenter cc ON bli.CostCenterID = cc.CostCenterID
    WHERE bli.FiscalPeriodID = :fiscal_period_id
    AND gla.IntercompanyFlag = TRUE;
    
    v_reconciled := (SELECT COUNT(*) FROM temp_intercompany_items);
    
    v_result_json := OBJECT_CONSTRUCT(
        'reconciliation_start', v_start_time,
        'reconciliation_end', CURRENT_TIMESTAMP(),
        'fiscal_period_id', :fiscal_period_id,
        'tolerance_amount', :tolerance_amount,
        'reconciled_count', v_reconciled,
        'variance_count', v_variances,
        'total_variance_amount', v_variance_total
    );
    
    DROP TABLE IF EXISTS temp_intercompany_items;
    
    RETURN v_result_json;
END;
$$;
