-- TABLE 4: AllocationRule
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.AllocationRule (
    AllocationRuleID        INT AUTOINCREMENT PRIMARY KEY,
    RuleCode                VARCHAR(30) NOT NULL,
    RuleName                VARCHAR(100) NOT NULL,
    RuleDescription         VARCHAR(500) NULL,
    RuleType                VARCHAR(20) NOT NULL,
    AllocationMethod        VARCHAR(20) NOT NULL,
    SourceCostCenterID      INT NULL,
    SourceCostCenterPattern VARCHAR(50) NULL,
    SourceAccountPattern    VARCHAR(50) NULL,
    TargetSpecification     VARIANT NOT NULL,
    AllocationBasis         VARCHAR(30) NULL,
    AllocationPercentage    DECIMAL(8,6) NULL,
    RoundingMethod          VARCHAR(10) NOT NULL DEFAULT 'NEAREST',
    RoundingPrecision       TINYINT NOT NULL DEFAULT 2,
    MinimumAmount           DECIMAL(19,4) NULL,
    ExecutionSequence       INT NOT NULL DEFAULT 100,
    DependsOnRuleID         INT NULL,
    EffectiveFromDate       DATE NOT NULL,
    EffectiveToDate         DATE NULL,
    IsActive                BOOLEAN NOT NULL DEFAULT TRUE,
    CreatedByUserID         INT NULL,
    CreatedDateTime         TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    ModifiedByUserID        INT NULL,
    ModifiedDateTime        TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    
    CONSTRAINT UQ_AllocationRule_Code UNIQUE (RuleCode),
    CONSTRAINT FK_AllocationRule_SourceCC FOREIGN KEY (SourceCostCenterID) 
        REFERENCES Planning.CostCenter (CostCenterID),
    CONSTRAINT FK_AllocationRule_DependsOn FOREIGN KEY (DependsOnRuleID) 
        REFERENCES Planning.AllocationRule (AllocationRuleID),
    CONSTRAINT CK_AllocationRule_Type CHECK (RuleType IN ('DIRECT','STEP_DOWN','RECIPROCAL','ACTIVITY_BASED')),
    CONSTRAINT CK_AllocationRule_Rounding CHECK (RoundingMethod IN ('NEAREST','UP','DOWN','NONE'))
);
