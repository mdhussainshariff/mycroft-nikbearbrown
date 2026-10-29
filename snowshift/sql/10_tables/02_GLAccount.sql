-- TABLE 2: GLAccount
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.GLAccount (
    GLAccountID             INT AUTOINCREMENT PRIMARY KEY,
    AccountNumber           VARCHAR(20) NOT NULL,
    AccountName             VARCHAR(150) NOT NULL,
    AccountType             CHAR(1) NOT NULL,
    AccountSubType          VARCHAR(30) NULL,
    ParentAccountID         INT NULL,
    AccountLevel            TINYINT NOT NULL DEFAULT 1,
    IsPostable              BOOLEAN NOT NULL DEFAULT TRUE,
    IsBudgetable            BOOLEAN NOT NULL DEFAULT TRUE,
    IsStatistical           BOOLEAN NOT NULL DEFAULT FALSE,
    NormalBalance           CHAR(1) NOT NULL DEFAULT 'D',
    CurrencyCode            CHAR(3) NOT NULL DEFAULT 'USD',
    ConsolidationAccountID  INT NULL,
    IntercompanyFlag        BOOLEAN NOT NULL DEFAULT FALSE,
    IsActive                BOOLEAN NOT NULL DEFAULT TRUE,
    CreatedDateTime         TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    ModifiedDateTime        TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    TaxCode                 VARCHAR(20) NULL,
    StatutoryAccountCode    VARCHAR(30) NULL,
    IFRSAccountCode         VARCHAR(30) NULL,
    
    CONSTRAINT UQ_GLAccount_Number UNIQUE (AccountNumber),
    CONSTRAINT FK_GLAccount_Parent FOREIGN KEY (ParentAccountID) 
        REFERENCES Planning.GLAccount (GLAccountID),
    CONSTRAINT CK_GLAccount_Type CHECK (AccountType IN ('A','L','E','R','X')),
    CONSTRAINT CK_GLAccount_Balance CHECK (NormalBalance IN ('D','C'))
);

ALTER TABLE Planning.GLAccount CLUSTER BY (AccountType, IsActive);
