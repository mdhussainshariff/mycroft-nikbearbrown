-- VIEW 2: Allocation Rule Targets
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE VIEW Planning.vw_AllocationRuleTargets AS
SELECT 
    ar.AllocationRuleID,
    ar.RuleCode,
    ar.RuleName,
    ar.RuleType,
    ar.AllocationMethod,
    ar.ExecutionSequence,
    target_spec.value:CostCenterID::INT AS TargetCostCenterID,
    target_spec.value:CostCenterCode::VARCHAR AS TargetCostCenterCode,
    target_spec.value:AllocationPercentage::DECIMAL(8,6) AS TargetAllocationPct,
    target_spec.value:Priority::INT AS TargetPriority,
    target_spec.value:AccountFilter::VARCHAR AS AccountFilter,
    target_spec.value:ExcludePattern::VARCHAR AS ExcludePattern,
    CASE WHEN target_spec.value:Conditions IS NOT NULL THEN TRUE ELSE FALSE END AS HasConditions,
    target_spec.value:Conditions AS ConditionsJson,
    cc.CostCenterName AS TargetCostCenterName,
    cc.ParentCostCenterID AS TargetParentCostCenterID,
    cc.IsActive AS TargetIsActive,
    ar.EffectiveFromDate,
    ar.EffectiveToDate,
    ar.IsActive AS RuleIsActive,
    CURRENT_TIMESTAMP() AS ViewGeneratedDateTime
FROM Planning.AllocationRule ar
JOIN LATERAL FLATTEN(INPUT => ar.TargetSpecification) target_spec
LEFT JOIN Planning.CostCenter cc 
    ON (cc.CostCenterID = target_spec.value:CostCenterID::INT
        OR cc.CostCenterCode = target_spec.value:CostCenterCode::VARCHAR)
WHERE ar.IsActive = TRUE;

GRANT SELECT ON VIEW Planning.vw_AllocationRuleTargets TO ROLE planning_analyst;
GRANT SELECT ON VIEW Planning.vw_AllocationRuleTargets TO ROLE planning_viewer;
