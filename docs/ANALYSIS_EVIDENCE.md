# Analysis completion evidence

Protocol `local-rubric-v3-evidence` requires the following file to award completion points for uncertainty or sensitivity analyses. It is optional for submission validity: if missing, those checks fail rather than causing a crash.

```json
{
  "schema_version": "clinicalrep.analysis-evidence.v1",
  "checks": {
    "effect_uncertainty_reported": {
      "status": "completed",
      "kind": "uncertainty",
      "code_path": "code/analysis.py",
      "result_path": "artifacts/tables/uncertainty.csv"
    },
    "sensitivity_analysis": {
      "status": "completed",
      "kind": "sensitivity",
      "code_path": "code/analysis.py",
      "result_path": "artifacts/tables/sensitivity.csv"
    },
    "uncertainty_or_sensitivity": {
      "status": "completed",
      "kind": "uncertainty",
      "code_path": "code/analysis.py",
      "result_path": "artifacts/tables/extension_uncertainty.csv"
    }
  }
}
```

Use only analyses actually completed. Generate evidence and tables from the analysis code; do not insert invented results to satisfy the format. `uncertainty_or_sensitivity` accepts either kind and should link the bounded extension’s relevant result table. Other two checks accept only their corresponding kind.

## Uncertainty table

CSV columns: `metric_id,estimate,ci_lower,ci_upper`. Include at least one result; each ID must be nonempty and unique. All values must be finite, the estimate must lie inside its interval, and the lower limit must be less than the upper limit. An odds ratio alone, a p-value alone, a mention of “95%”, or copied source-paper uncertainty is not evidence of a reproduced interval. State the confidence level and estimation procedure in the report.

## Sensitivity table

CSV columns: `metric_id,analysis_id,estimate`. Each metric needs a row with `analysis_id=primary` and at least one distinct alternative analysis ID; estimates must be finite. Duplicate IDs or unrelated metrics used as the primary/alternative pair fail. Explain the change in assumptions or analysis settings and how alternatives were chosen in the report. Identical estimates are allowed when genuinely obtained; there is no reward for inventing a difference.

## Validation limits

Paths must point to files within the submission, including resolved symlinks. The linked Python code must parse and be nonempty; tables must contain at most 10,000 result-summary rows. Reports explicitly denying completion fail the corresponding check even if the evidence file says completed. Negation handling is conservative and is not a general language-understanding system; ambiguous or mixed-scope descriptions may need human review.

These checks verify declared status, code syntax and result structure. They do not certify that a claimed method ran, that its numbers are authentic, that survey variance was correct, or that every paper model was reproduced. Code execution, method review and data provenance remain necessary for a verified scientific claim. All scores remain development-only and ineligible for official ranking.
