-- TVP REPLACEMENT 2: AllocationResultTableType
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.AllocationResultStaging (
    AllocationSessionID     VARCHAR(36) NOT NULL,
    SourceBudgetLineItemID  BIGINT NOT NULL,
    TargetCostCenterID      INT NOT NULL,
    TargetGLAccountID       INT NOT NULL,
    AllocatedAmount         DECIMAL(19,4) NOT NULL,
    AllocationPercentage    DECIMAL(8,6) NOT NULL,
    AllocationRuleID        INT NOT NULL,
    ProcessingSequence      INT NOT NULL,
    CreatedDateTime         TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (AllocationSessionID, SourceBudgetLineItemID, TargetCostCenterID, TargetGLAccountID)
);

CREATE OR REPLACE PROCEDURE Planning.CLEANUP_ALLOCATION_RESULTS(
    p_hours_old INT DEFAULT 24
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    v_deleted_count INT;
BEGIN
    DELETE FROM Planning.AllocationResultStaging
    WHERE CreatedDateTime < DATEADD(hour, -:p_hours_old, CURRENT_TIMESTAMP());
    
    LET v_deleted_count := (SELECT ROW_COUNT());
    RETURN 'Deleted ' || :v_deleted_count || ' old allocation results';
END;
$$;
