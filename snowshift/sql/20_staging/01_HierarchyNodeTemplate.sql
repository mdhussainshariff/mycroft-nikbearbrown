-- TVP REPLACEMENT 1: HierarchyNodeTableType
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.HierarchyNodeTemplate (
    NodeID                  INT NOT NULL,
    ParentNodeID            INT NULL,
    NodeLevel               INT NOT NULL,
    NodePath                VARCHAR(500) NOT NULL,
    SortOrder               INT NOT NULL,
    IsLeaf                  BOOLEAN NOT NULL,
    AggregationWeight       DECIMAL(8,6) NOT NULL DEFAULT 1.0,
    PRIMARY KEY (NodeID)
);

CREATE OR REPLACE PROCEDURE Planning.PROCESS_HIERARCHY_JSON(
    p_hierarchy_json VARIANT
)
RETURNS TABLE (
    NodeID INT,
    ParentNodeID INT,
    NodeLevel INT,
    NodePath VARCHAR,
    SortOrder INT,
    IsLeaf BOOLEAN,
    AggregationWeight DECIMAL(8,6)
)
LANGUAGE SQL
AS
$$
    SELECT
        value:NodeID::INT AS NodeID,
        value:ParentNodeID::INT AS ParentNodeID,
        value:NodeLevel::INT AS NodeLevel,
        value:NodePath::VARCHAR AS NodePath,
        value:SortOrder::INT AS SortOrder,
        value:IsLeaf::BOOLEAN AS IsLeaf,
        value:AggregationWeight::DECIMAL(8,6) AS AggregationWeight
    FROM TABLE(FLATTEN(INPUT => p_hierarchy_json));
$$;
