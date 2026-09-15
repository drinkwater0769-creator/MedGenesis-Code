# ClinicalRepBench Task: Oncology_000

You are evaluating an autonomous clinical-research agent on a redacted paper-reproduction task.

## Primary Question

Can an autonomous clinical-research agent reproduce and critically extend the TCGA lung adenocarcinoma molecular-profile workflow using open GDC clinical cases and masked WXS somatic mutation MAF files?

## Required Work

1. Reconstruct the TCGA-LUAD cohort, sequencing denominator, driver-gene alteration definitions, clinical endpoint availability, covariates, and statistical analysis plan.
2. Produce a Re-Discovery analysis that recovers core LUAD driver alteration patterns from PMID 25079552, including TP53, KRAS, EGFR, STK11, and KEAP1 frequencies and EGFR/KRAS near-mutual-exclusion.
3. Explicitly align the open-data reproduction to the Nature 2014 TCGA lung adenocarcinoma paper: molecular subtype frame, tumor stage/TNM availability, survival endpoint availability, and multi-platform modalities that cannot be recovered from open masked MAF data alone.
4. Produce a New-Discovery analysis that identifies a plausible additional signal, subgroup, limitation, or deployment implication from the same clinical-genomic evidence space, with uncertainty boundaries or a sensitivity analysis.
5. Separate statistical significance from clinical significance.
6. Identify assumptions, missingness, confounding, bias, data leakage risk, and generalizability limits.
7. Do not infer causality unless the design and assumptions justify it.
8. Submit executable analysis code at `code/analysis.py`. The script must rebuild the patient-level mutation matrix from raw `data/source/tcga-luad_cases.json`, `data/source/tcga-luad_masked_maf_files.json`, and MAF files under `data/source/tcga-luad_maf/`; it must not rely on precomputed `analytic_extract.csv` driver columns.

## Clinical Task Frame

- Domain: Oncology and cancer genomics
- Endpoint: molecular subtype and survival availability in lung adenocarcinoma
- Re-Discovery target: Reproduce major LUAD driver mutation frequencies and EGFR/KRAS near-mutual-exclusion using GDC masked somatic mutations.
- New-Discovery target: Evaluate a compact, clinically interpretable EGFR/KRAS exclusivity signal and its limitations as a benchmark check.
- Scoring frame: criterion-level research-quality scoring. Merely creating all files or matching a few numeric endpoints is not sufficient for a high score.

## Required Report Sections

- `## Methods`
- `## Re-Discovery`
- `## New-Discovery`
- `## Results`
- `## Limitations`
- `## Clinical Safety`

## Required Artifacts

- `submission.json`
- `code/analysis.py`
- `report/report.md`
- `artifacts/primary_metrics.json`
- `artifacts/tables/table1.csv`
- `artifacts/tables/table2.csv`
- `artifacts/tables/table3.csv`
- `artifacts/figures/figure1.svg`
