-- TABLE 8: ConsolidationJournalLine
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.ConsolidationJournalLine (
    JournalLineID           BIGINT AUTOINCREMENT PRIMARY KEY,
    JournalID               BIGINT NOT NULL,
    LineNumber              INT NOT NULL,
    GLAccountID             INT NOT NULL,
    CostCenterID            INT NOT NULL,
    DebitAmount             DECIMAL(19,4) NOT NULL DEFAULT 0,
    CreditAmount            DECIMAL(19,4) NOT NULL DEFAULT 0,
    NetAmount               DECIMAL(19,4) NOT NULL DEFAULT 0,
    LocalCurrencyCode       CHAR(3) NOT NULL DEFAULT 'USD',
    LocalCurrencyAmount     DECIMAL(19,4) NULL,
    ExchangeRate            DECIMAL(18,10) NULL,
    Description             VARCHAR(255) NULL,
    ReferenceNumber         VARCHAR(50) NULL,
    PartnerEntityCode       VARCHAR(20) NULL,
    PartnerAccountID        INT NULL,
    StatisticalQuantity     DECIMAL(18,6) NULL,
    StatisticalUOM          VARCHAR(10) NULL,
    AllocationRuleID        INT NULL,
    CreatedDateTime         TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    
    CONSTRAINT UQ_ConsolidationJournalLine_JournalLine UNIQUE (JournalID, LineNumber),
    CONSTRAINT FK_ConsolidationJournalLine_Journal FOREIGN KEY (JournalID) 
        REFERENCES Planning.ConsolidationJournal (JournalID) ON DELETE CASCADE,
    CONSTRAINT FK_ConsolidationJournalLine_Account FOREIGN KEY (GLAccountID) 
        REFERENCES Planning.GLAccount (GLAccountID),
    CONSTRAINT FK_ConsolidationJournalLine_CostCenter FOREIGN KEY (CostCenterID) 
        REFERENCES Planning.CostCenter (CostCenterID),
    CONSTRAINT FK_ConsolidationJournalLine_AllocationRule FOREIGN KEY (AllocationRuleID) 
        REFERENCES Planning.AllocationRule (AllocationRuleID),
    CONSTRAINT CK_ConsolidationJournalLine_DebitCredit CHECK (
        (DebitAmount >= 0 AND CreditAmount >= 0) AND
        NOT (DebitAmount > 0 AND CreditAmount > 0)
    )
);

ALTER TABLE Planning.ConsolidationJournalLine CLUSTER BY (JournalID);
