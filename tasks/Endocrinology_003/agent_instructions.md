# ClinicalRepBench Task: Endocrinology_003

You are evaluating an autonomous clinical-research agent on a redacted paper-reproduction task.

## Primary Question

Can an autonomous clinical-research agent reproduce the main analysis of PMID 37755728 (Prevalence and Overlap of Cardiac, Renal, and Metabolic Conditions in US Adults, 1999-2020) using NHANES or its governed benchmark extract?

## Required Work

1. Reconstruct the likely study design, analytic cohort, exposure or predictor, endpoint, covariates, and statistical analysis plan.
2. Produce a Re-Discovery analysis that tests whether the source study's main finding can be recovered.
3. Produce a New-Discovery analysis that identifies a plausible additional signal, subgroup, limitation, or deployment implication from the same evidence space.
4. Separate statistical significance from clinical significance.
5. Identify assumptions, missingness, confounding, bias, data leakage risk, and generalizability limits.
6. Do not infer causality unless the design and assumptions justify it.

## Clinical Task Frame

- Domain: Endocrinology
- Endpoint: prevalence and overlap of cardiac, renal, and metabolic conditions
- Re-Discovery target: Recover the reported renal-risk reduction under confounding control.
- New-Discovery target: Evaluate falsification endpoints and residual confounding signals.

## Required Report Sections

- `## Methods`
- `## Re-Discovery`
- `## New-Discovery`
- `## Results`
- `## Limitations`
- `## Clinical Safety`

## Required Artifacts

- `submission.json`
- `report/report.md`
- `artifacts/primary_metrics.json`
- `artifacts/tables/table1.csv`
- `artifacts/tables/table2.csv`
- `artifacts/figures/figure1.svg`
