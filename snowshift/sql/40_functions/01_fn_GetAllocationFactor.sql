-- FUNCTION 1: GetAllocationFactor
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE FUNCTION Planning.fn_GetAllocationFactor(
    p_source_cc_id INT,
    p_target_cc_id INT,
    p_allocation_basis VARCHAR,
    p_fiscal_period_id INT,
    p_budget_header_id INT
)
RETURNS DECIMAL(18,10)
LANGUAGE SQL
IMMUTABLE
AS
$$
    CASE 
        WHEN p_allocation_basis = 'EQUAL' THEN 
            1.0 / COALESCE((
                SELECT COUNT(DISTINCT CostCenterID)
                FROM Planning.BudgetLineItem
                WHERE BudgetHeaderID = p_budget_header_id
                AND FiscalPeriodID = p_fiscal_period_id
            ), 1)
        WHEN p_allocation_basis = 'HEADCOUNT' THEN 
            COALESCE((
                SELECT COALESCE(AllocationWeight, 1.0)
                FROM Planning.CostCenter
                WHERE CostCenterID = p_target_cc_id
            ), 1.0)
        ELSE 1.0
    END
$$;
