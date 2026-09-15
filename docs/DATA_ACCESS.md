# Data access

No original or derived participant-level datasets are bundled.

## Source classes

There are 15 original open-data tasks (NHANES 10, TCGA/GDC 4, FAERS 1), 17 direct UKB tasks, 6 mixed-source tasks, and 2 repository-summary-statistics tasks. The latter two were previously mislabeled UKB participant tasks. They are not automatically supported by the open-data downloader.

Start open-data tasks with `ccb plan-open-data TASK`. Downloads and task-specific extraction may contact provider services; record actual versions and download dates. A valid download plan does not establish cohort or paper-method equivalence. Reference-analysis helpers are public development utilities; disclose their use in an agent evaluation.

## UKB and mixed-source tasks

Obtain data through your own authorized access. Follow [UKB workflow](UKB_WORKFLOW.md) for exported CSV/TSV/Parquet files. Preparation runs within your authorized environment; no account, data access, or managed UKB service is supplied.

Each of the 25 reclassified tasks has a `data/source_contract.json` listing source references, candidate fields where available, and unresolved requirements. Candidate fields are not a complete paper extraction specification. Availability checks do not establish units, encodings, ancestry, covariate definitions, or the original data freeze. Mixed-source studies additionally need their discovery/validation cohorts, model parameters, or summary statistics.

The replaced generic cohort SQL and phenotype templates are explicitly unfrozen. Do not treat a comment-only SQL file as an extractor. See [source readiness](SOURCE_READINESS.md) for task-level status.

## Reproducibility and sharing

Declare source release, withdrawals status, coding dictionaries, phenotype exclusions, follow-up cutoff, covariates and model settings. Record any deviations before comparing with paper values. Different source snapshots can change cohort sizes and effects; do not tune exclusions to hit a published sample size.

Keep participant data and private results outside the public repository. Submit only permitted code and participant-free artifacts. `.gitignore` and `audit_public_release.py` are supplementary checks, not proof that an arbitrary artifact is safe to publish.
