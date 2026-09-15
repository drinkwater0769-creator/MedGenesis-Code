-- ClinicalRepBench scaffold cohort definition for Endocrinology_003.
-- Replace table names with the locked benchmark extract in governed releases.
WITH eligible_source AS (
  SELECT *
  FROM analysis_dataset
  WHERE source_study_task_id = 'Endocrinology_003'
), analytic_cohort AS (
  SELECT *
  FROM eligible_source
  WHERE meets_inclusion_criteria = 1
    AND meets_exclusion_criteria = 0
)
SELECT * FROM analytic_cohort;
