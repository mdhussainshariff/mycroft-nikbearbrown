-- TABLE 3: CostCenter
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.CostCenter (
    CostCenterID            INT AUTOINCREMENT PRIMARY KEY,
    CostCenterCode          VARCHAR(20) NOT NULL,
    CostCenterName          VARCHAR(100) NOT NULL,
    ParentCostCenterID      INT NULL,
    HierarchyLevel          INT NULL,
    ManagerEmployeeID       INT NULL,
    DepartmentCode          VARCHAR(10) NULL,
    IsActive                BOOLEAN NOT NULL DEFAULT TRUE,
    EffectiveFromDate       DATE NOT NULL,
    EffectiveToDate         DATE NULL,
    AllocationWeight        DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
    ValidFrom               TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    ValidTo                 TIMESTAMP_NTZ NULL,
    
    CONSTRAINT UQ_CostCenter_Code UNIQUE (CostCenterCode),
    CONSTRAINT FK_CostCenter_Parent FOREIGN KEY (ParentCostCenterID) 
        REFERENCES Planning.CostCenter (CostCenterID),
    CONSTRAINT CK_CostCenter_Weight CHECK (AllocationWeight BETWEEN 0 AND 1)
);

ALTER TABLE Planning.CostCenter CLUSTER BY (IsActive, EffectiveFromDate);

-- Create history table
CREATE TABLE IF NOT EXISTS Planning.CostCenterHistory (
    CostCenterID            INT NOT NULL,
    CostCenterCode          VARCHAR(20) NOT NULL,
    CostCenterName          VARCHAR(100) NOT NULL,
    ParentCostCenterID      INT NULL,
    HierarchyLevel          INT NULL,
    ManagerEmployeeID       INT NULL,
    DepartmentCode          VARCHAR(10) NULL,
    IsActive                BOOLEAN NOT NULL,
    EffectiveFromDate       DATE NOT NULL,
    EffectiveToDate         DATE NULL,
    AllocationWeight        DECIMAL(5,4) NOT NULL,
    ValidFrom               TIMESTAMP_NTZ NOT NULL,
    ValidTo                 TIMESTAMP_NTZ NOT NULL,
    ChangeDateTime          TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
