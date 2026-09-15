# Submissions for Oncology_000

A valid submission should include:

- `submission.json`
- `code/analysis.py`
- `report/report.md`
- `artifacts/primary_metrics.json`
- `artifacts/tables/table1.csv`
- `artifacts/tables/table2.csv`
- `artifacts/tables/table3.csv`
- `artifacts/figures/figure1.svg`

`code/analysis.py` must be executable from the submission root and must rebuild the cohort and driver mutation matrix from raw GDC clinical JSON plus masked somatic MAF files under `data/source/`. The scorer reruns this script on a hidden raw TCGA-LUAD mini fixture. Final scoring also uses a criterion-level research-quality rubric: matching a few static numeric metrics or creating all files is not enough for a high score. Submissions must explicitly align the open-data result to PMID 25079552, discuss survival/TNM availability and multi-platform gaps, and separate statistical evidence from clinical utility.

`artifacts/primary_metrics.json` should report the locked Oncology_000 metric IDs used by the scorer.
