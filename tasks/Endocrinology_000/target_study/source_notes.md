# Source Notes: Endocrinology_000

## Bound Literature

- PMID: 37567907
- Title: Comparisons of the prediction models for undiagnosed diabetes between machine learning versus traditional statistical methods
- Journal/date: Sci Rep (2023 Aug 11)
- DOI: 10.1038/s41598-023-40170-0
- PubMed: https://pubmed.ncbi.nlm.nih.gov/37567907/

## Data Source

- Dataset: NHANES
- Access: open
- URL: https://wwwn.cdc.gov/nchs/nhanes/
- Description: CDC National Health and Nutrition Examination Survey public-use files.

## Reproduction Target

Reconstruct the source study's cohort, variables, outcome definition, statistical analysis, and main reported conclusion using the official data source or a locked benchmark extract derived from it.

## Primary Endpoint

undiagnosed diabetes prediction

## New-Discovery Extension

After reproducing the source analysis, test one conservative extension: a prespecified subgroup, calibration/fairness check, sensitivity analysis, or deployment-risk analysis that remains within the source data's support.

## Leakage and Licensing

The benchmark may cite the paper and PubMed metadata, but it must not redistribute copyrighted full text, non-public source tables, or controlled patient-level records. For public release, provide extraction code and provenance; for controlled data, provide execution instructions and scoring targets in a governed environment.

## Data-binding audit note (2026-08-26 local reproduction)

The bound paper (PMID 37567907) analyzes the **Korean** National Health and
Nutrition Examination Survey (KNHANES 2014-2020, N = 32,827), not the US
NHANES that this task's data manifest points to. KNHANES microdata requires
registration at knhanes.kdca.go.kr. A faithful numeric reproduction therefore
cannot run from the US NHANES files; the current launcher's extract-integrity
output should not be read as a paper reproduction. Options recorded for the
benchmark maintainers: (a) treat this task as registration-gated (KNHANES),
or (b) keep the US-NHANES launcher as an explicitly labeled analog task with
its own locked targets. No paper swap was made, preserving the 40-task freeze.
