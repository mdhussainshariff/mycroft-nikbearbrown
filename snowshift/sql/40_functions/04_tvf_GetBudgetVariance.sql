-- FUNCTION 4: GetBudgetVariance (Table-Valued)
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE FUNCTION Planning.tvf_GetBudgetVariance(
    p_budget_header_id INT,
    p_fiscal_period_id INT
)
RETURNS TABLE (
    GLAccountID INT,
    CostCenterID INT,
    OriginalAmount DECIMAL(19,4),
    AdjustedAmount DECIMAL(19,4),
    FinalAmount DECIMAL(19,4),
    VarianceAmount DECIMAL(19,4),
    VariancePercent DECIMAL(10,2)
)
LANGUAGE SQL
AS
$$
    SELECT 
        GLAccountID,
        CostCenterID,
        OriginalAmount,
        AdjustedAmount,
        FinalAmount,
        AdjustedAmount AS VarianceAmount,
        CASE 
            WHEN OriginalAmount != 0 THEN (AdjustedAmount / OriginalAmount) * 100
            ELSE 0
        END AS VariancePercent
    FROM Planning.BudgetLineItem
    WHERE BudgetHeaderID = p_budget_header_id
    AND FiscalPeriodID = p_fiscal_period_id
    AND AdjustedAmount != 0
$$;
