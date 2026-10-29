-- STEP 1: Set Warehouse and Database Context
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE WAREHOUSE MIGRATION_WH WITH
  WAREHOUSE_SIZE = 'MEDIUM'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE;

CREATE OR REPLACE DATABASE SNOWCONVERT_DEMO
  COMMENT = 'Financial Planning Schema Migration';

USE WAREHOUSE MIGRATION_WH;
USE DATABASE SNOWCONVERT_DEMO;
