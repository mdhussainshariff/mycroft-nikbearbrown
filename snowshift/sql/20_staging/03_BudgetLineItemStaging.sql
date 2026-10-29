-- TVP REPLACEMENT 3: BudgetLineItemTableType
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.BudgetLineItemStaging (
    StagingBatchID          VARCHAR(36) NOT NULL,
    GLAccountID             INT NOT NULL,
    CostCenterID            INT NOT NULL,
    FiscalPeriodID          INT NOT NULL,
    OriginalAmount          DECIMAL(19,4) NOT NULL,
    AdjustedAmount          DECIMAL(19,4) NULL,
    SpreadMethodCode        VARCHAR(10) NULL,
    Notes                   VARCHAR(500) NULL,
    LineSequence            INT NOT NULL,
    RowStatus               VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    ErrorMessage            VARCHAR(1000) NULL,
    CreatedDateTime         TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    LoadedDateTime          TIMESTAMP_NTZ NULL,
    PRIMARY KEY (StagingBatchID, GLAccountID, CostCenterID, FiscalPeriodID)
);
