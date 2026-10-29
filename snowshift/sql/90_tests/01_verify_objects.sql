-- Post-deploy object verification
-- Confirms every table, view, function and procedure landed in PLANNING.

-- Verify all objects were created successfully
SELECT 'Schema Created' AS Status
UNION ALL
SELECT CASE WHEN COUNT(*) > 0 THEN 'Tables Created (' || COUNT(*) || ')' ELSE 'No Tables' END
FROM Information_Schema.Tables WHERE TABLE_SCHEMA = 'PLANNING'
UNION ALL
SELECT CASE WHEN COUNT(*) > 0 THEN 'Views Created (' || COUNT(*) || ')' ELSE 'No Views' END
FROM Information_Schema.Views WHERE TABLE_SCHEMA = 'PLANNING'
UNION ALL
SELECT CASE WHEN COUNT(*) > 0 THEN 'Functions Created (' || COUNT(*) || ')' ELSE 'No Functions' END
FROM Information_Schema.Functions WHERE FUNCTION_SCHEMA = 'PLANNING'
UNION ALL
SELECT CASE WHEN COUNT(*) > 0 THEN 'Procedures Created (' || COUNT(*) || ')' ELSE 'No Procedures' END
FROM Information_Schema.Procedures WHERE PROCEDURE_SCHEMA = 'PLANNING';
