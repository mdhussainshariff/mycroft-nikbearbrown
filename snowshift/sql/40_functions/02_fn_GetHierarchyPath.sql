-- FUNCTION 2: GetHierarchyPath
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE FUNCTION Planning.fn_GetHierarchyPath(
    p_cost_center_id INT
)
RETURNS VARCHAR
LANGUAGE SQL
IMMUTABLE
AS
$$
    WITH RECURSIVE HierarchyPath AS (
        SELECT 
            CostCenterID,
            CostCenterCode,
            ParentCostCenterID,
            1 AS Level,
            CostCenterCode AS Path
        FROM Planning.CostCenter
        WHERE CostCenterID = p_cost_center_id
        
        UNION ALL
        
        SELECT 
            cc.CostCenterID,
            cc.CostCenterCode,
            cc.ParentCostCenterID,
            hp.Level + 1,
            cc.CostCenterCode || '/' || hp.Path
        FROM Planning.CostCenter cc
        INNER JOIN HierarchyPath hp ON cc.CostCenterID = hp.ParentCostCenterID
        WHERE hp.Level < 20
    )
    SELECT Path
    FROM HierarchyPath
    WHERE CostCenterID = p_cost_center_id
    ORDER BY Level DESC
    LIMIT 1
$$;
