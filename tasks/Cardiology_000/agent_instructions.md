# ClinicalRepBench Task: Cardiology_000

You are evaluating an autonomous clinical-research agent on a redacted paper-reproduction task.

## Primary Question

Can an autonomous clinical-research agent reproduce the main analysis of PMID 41163015 (Associations between triglyceride-glucose-related indices and all-cause and cardiovascular mortality among individuals with atrial fibrillation and metabolic syndrome: a cohort study of the UK biobank) using UK Biobank or a governed benchmark extract?

## Required Work

1. Reconstruct the likely study design, analytic cohort, exposure or predictor, endpoint, covariates, and statistical analysis plan.
2. Produce a Re-Discovery analysis that tests whether the source study's main finding can be recovered.
3. Produce a New-Discovery analysis that identifies a plausible additional signal, subgroup, limitation, or deployment implication from the same evidence space.
4. Separate statistical significance from clinical significance.
5. Identify assumptions, missingness, confounding, bias, data leakage risk, and generalizability limits.
6. Do not infer causality unless the design and assumptions justify it.

## Clinical Task Frame

- Domain: Cardiology
- Endpoint: all-cause and cardiovascular mortality among UK Biobank participants with atrial fibrillation and metabolic syndrome
- Re-Discovery target: Reconstruct the source study analysis for: all-cause and cardiovascular mortality among UK Biobank participants with atrial fibrillation and metabolic syndrome. Declare any deviations or missing modules.
- New-Discovery target: Perform one prespecified, data-supported sensitivity or subgroup analysis; distinguish it from source reproduction and report uncertainty.

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

## Source contract and evaluation status

Read `data/source_contract.json` before accessing data. This task is not currently eligible for a formal leaderboard score. Report missing inputs and distinguish the named development profile from full-paper reproduction.
