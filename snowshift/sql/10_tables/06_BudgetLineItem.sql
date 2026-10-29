-- TABLE 6: BudgetLineItem
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.BudgetLineItem (
    BudgetLineItemID        BIGINT AUTOINCREMENT PRIMARY KEY,
    BudgetHeaderID          INT NOT NULL,
    GLAccountID             INT NOT NULL,
    CostCenterID            INT NOT NULL,
    FiscalPeriodID          INT NOT NULL,
    OriginalAmount          DECIMAL(19,4) NOT NULL DEFAULT 0,
    AdjustedAmount          DECIMAL(19,4) NOT NULL DEFAULT 0,
    FinalAmount             DECIMAL(19,4) NOT NULL DEFAULT 0,
    LocalCurrencyAmount     DECIMAL(19,4) NULL,
    ReportingCurrencyAmount DECIMAL(19,4) NULL,
    StatisticalQuantity     DECIMAL(18,6) NULL,
    UnitOfMeasure           VARCHAR(10) NULL,
    SpreadMethodCode        VARCHAR(10) NULL,
    SeasonalityFactor       DECIMAL(8,6) NULL,
    SourceSystem            VARCHAR(30) NULL,
    SourceReference         VARCHAR(100) NULL,
    ImportBatchID           VARCHAR(36) NULL,
    IsAllocated             BOOLEAN NOT NULL DEFAULT FALSE,
    AllocationSourceLineID  BIGINT NULL,
    AllocationPercentage    DECIMAL(8,6) NULL,
    LastModifiedByUserID    INT NULL,
    LastModifiedDateTime    TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    RowHash                 VARCHAR(64) NULL,
    
    CONSTRAINT FK_BudgetLineItem_Header FOREIGN KEY (BudgetHeaderID) 
        REFERENCES Planning.BudgetHeader (BudgetHeaderID),
    CONSTRAINT FK_BudgetLineItem_Account FOREIGN KEY (GLAccountID) 
        REFERENCES Planning.GLAccount (GLAccountID),
    CONSTRAINT FK_BudgetLineItem_CostCenter FOREIGN KEY (CostCenterID) 
        REFERENCES Planning.CostCenter (CostCenterID),
    CONSTRAINT FK_BudgetLineItem_Period FOREIGN KEY (FiscalPeriodID) 
        REFERENCES Planning.FiscalPeriod (FiscalPeriodID),
    CONSTRAINT FK_BudgetLineItem_AllocationSource FOREIGN KEY (AllocationSourceLineID) 
        REFERENCES Planning.BudgetLineItem (BudgetLineItemID)
);

ALTER TABLE Planning.BudgetLineItem CLUSTER BY (BudgetHeaderID, FiscalPeriodID);
ALTER TABLE Planning.BudgetLineItem ADD CONSTRAINT idx_BudgetLineItem_NaturalKey
    UNIQUE (BudgetHeaderID, GLAccountID, CostCenterID, FiscalPeriodID);
