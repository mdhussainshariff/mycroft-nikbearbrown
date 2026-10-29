-- STEP 3: Create Roles and Permissions
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE ROLE IF NOT EXISTS planning_admin;
CREATE ROLE IF NOT EXISTS planning_analyst;
CREATE ROLE IF NOT EXISTS planning_viewer;

-- Planning Admin Role - Full Permissions
GRANT USAGE ON DATABASE SNOWCONVERT_DEMO TO ROLE planning_admin;
GRANT USAGE, CREATE TABLE, CREATE VIEW, CREATE PROCEDURE ON SCHEMA Planning TO ROLE planning_admin;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA Planning TO ROLE planning_admin;
GRANT SELECT ON ALL VIEWS IN SCHEMA Planning TO ROLE planning_admin;

-- Planning Analyst Role - Read/Write
GRANT USAGE ON DATABASE SNOWCONVERT_DEMO TO ROLE planning_analyst;
GRANT USAGE ON SCHEMA Planning TO ROLE planning_analyst;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA Planning TO ROLE planning_analyst;
GRANT SELECT ON ALL VIEWS IN SCHEMA Planning TO ROLE planning_analyst;

-- Planning Viewer Role - Read Only
GRANT USAGE ON DATABASE SNOWCONVERT_DEMO TO ROLE planning_viewer;
GRANT USAGE ON SCHEMA Planning TO ROLE planning_viewer;
GRANT SELECT ON ALL TABLES IN SCHEMA Planning TO ROLE planning_viewer;
GRANT SELECT ON ALL VIEWS IN SCHEMA Planning TO ROLE planning_viewer;
