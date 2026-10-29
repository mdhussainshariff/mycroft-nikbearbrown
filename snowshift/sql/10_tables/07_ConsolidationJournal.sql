-- TABLE 7: ConsolidationJournal
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE TABLE IF NOT EXISTS Planning.ConsolidationJournal (
    JournalID               BIGINT AUTOINCREMENT PRIMARY KEY,
    JournalNumber           VARCHAR(30) NOT NULL,
    JournalType             VARCHAR(20) NOT NULL,
    BudgetHeaderID          INT NOT NULL,
    FiscalPeriodID          INT NOT NULL,
    PostingDate             DATE NOT NULL,
    Description             VARCHAR(500) NULL,
    StatusCode              VARCHAR(15) NOT NULL DEFAULT 'DRAFT',
    SourceEntityCode        VARCHAR(20) NULL,
    TargetEntityCode        VARCHAR(20) NULL,
    IsAutoReverse           BOOLEAN NOT NULL DEFAULT FALSE,
    ReversalPeriodID        INT NULL,
    ReversedFromJournalID   BIGINT NULL,
    IsReversed              BOOLEAN NOT NULL DEFAULT FALSE,
    TotalDebits             DECIMAL(19,4) NOT NULL DEFAULT 0,
    TotalCredits            DECIMAL(19,4) NOT NULL DEFAULT 0,
    IsBalanced              BOOLEAN NOT NULL DEFAULT FALSE,
    PreparedByUserID        INT NULL,
    PreparedDateTime        TIMESTAMP_NTZ NULL,
    ReviewedByUserID        INT NULL,
    ReviewedDateTime        TIMESTAMP_NTZ NULL,
    ApprovedByUserID        INT NULL,
    ApprovedDateTime        TIMESTAMP_NTZ NULL,
    PostedByUserID          INT NULL,
    PostedDateTime          TIMESTAMP_NTZ NULL,
    AttachmentReference     VARCHAR(36) NULL,
    AttachmentRowGuid       VARCHAR(36) NOT NULL DEFAULT UUID_STRING(),
    
    CONSTRAINT UQ_ConsolidationJournal_Number UNIQUE (JournalNumber),
    CONSTRAINT FK_ConsolidationJournal_Header FOREIGN KEY (BudgetHeaderID) 
        REFERENCES Planning.BudgetHeader (BudgetHeaderID),
    CONSTRAINT FK_ConsolidationJournal_Period FOREIGN KEY (FiscalPeriodID) 
        REFERENCES Planning.FiscalPeriod (FiscalPeriodID),
    CONSTRAINT FK_ConsolidationJournal_ReversalPeriod FOREIGN KEY (ReversalPeriodID) 
        REFERENCES Planning.FiscalPeriod (FiscalPeriodID),
    CONSTRAINT FK_ConsolidationJournal_ReversedFrom FOREIGN KEY (ReversedFromJournalID) 
        REFERENCES Planning.ConsolidationJournal (JournalID)
);
