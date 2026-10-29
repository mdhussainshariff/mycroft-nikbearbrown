-- FUNCTION 3: ExplodeCostCenterHierarchy (Table-Valued)
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE FUNCTION Planning.tvf_ExplodeCostCenterHierarchy(
    p_root_cost_center_id INT
)
RETURNS TABLE (
    CostCenterID INT,
    CostCenterCode VARCHAR,
    CostCenterName VARCHAR,
    ParentCostCenterID INT,
    HierarchyLevel INT,
    HierarchyPath VARCHAR
)
LANGUAGE SQL
AS
$$
    WITH RECURSIVE CostCenterHierarchy AS (
        SELECT 
            CostCenterID,
            CostCenterCode,
            CostCenterName,
            ParentCostCenterID,
            0 AS HierarchyLevel,
            CostCenterCode AS HierarchyPath
        FROM Planning.CostCenter
        WHERE CostCenterID = p_root_cost_center_id
        AND IsActive = TRUE
        
        UNION ALL
        
        SELECT 
            cc.CostCenterID,
            cc.CostCenterCode,
            cc.CostCenterName,
            cc.ParentCostCenterID,
            cch.HierarchyLevel + 1,
            cch.HierarchyPath || '/' || cc.CostCenterCode
        FROM Planning.CostCenter cc
        INNER JOIN CostCenterHierarchy cch ON cc.ParentCostCenterID = cch.CostCenterID
        WHERE cc.IsActive = TRUE
        AND cch.HierarchyLevel < 20
    )
    SELECT *
    FROM CostCenterHierarchy
$$;
