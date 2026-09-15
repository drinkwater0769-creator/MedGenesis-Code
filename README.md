# ClinicalRepBench

**Development preview — welcome to trial tasks and report issues. Current scores are not for official rankings.**

A clinical paper-reproduction benchmark for autonomous research agents.

ClinicalRepBench evaluates reconstruction of a published study, reproduction of its main findings, and a bounded additional analysis. It contains **40 tasks across 10 clinical domains**, with four tasks per domain.

This is the **public development release `0.4.3-public.5`**, based on task design `0.4.1-source-contracts`. It includes task specifications, public development targets, data preparation tools and a local scorer. No historical model scores, experiment logs or leaderboard results are included.

中文说明：[发布说明与参与边界](docs/发布说明_中文.md)。

## Task tracks

|Track|Tasks|Data sources|Participation|
|---|---:|---|---|
|Open data|15|NHANES (10), TCGA/GDC (4), FAERS (1)|Obtain data from the linked providers using the preparation tools or a documented equivalent workflow|
|Direct UKB|17|UK Biobank participant data|Your own approved access and compatible exports|
|Mixed sources|6|UKB plus other cohorts or summary statistics|UKB access alone is insufficient|
|Repository statistics|2|GWAS summary statistics and annotation|Use each paper’s repositories; individual UKB exports are insufficient|

Domains: Oncology, Cardiology, Neurology, Infectious Disease, Endocrinology, Immunology, Respiratory, Gastroenterology, Hematology and Dermatology.

Browse the [task index](docs/clinicalrepbench_task_index.md), [paper mapping](docs/clinicalrepbench_literature_map.md) and [release limitations](docs/RELEASE_NOTES.md).

## Quick start

Run these commands from the repository root with Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python scripts/audit_public_release.py
ccb validate-task tasks/Endocrinology_001
ccb plan-open-data tasks/Endocrinology_001
```

Create a workspace and prepare the open data:

```bash
ccb prepare-run tasks/Endocrinology_001 workspaces/my_run
ccb prepare-open-data tasks/Endocrinology_001 workspaces/my_run --cache-dir .cache/nhanes --download
```

Give your agent the workspace and its `agent_instructions.md`. The preparation tool does not launch an agent. Complete the study and produce the files in the [submission contract](docs/SUBMISSION.md), then validate and score:

```bash
ccb validate-submission tasks/Endocrinology_001 workspaces/my_run
ccb score-submission tasks/Endocrinology_001 workspaces/my_run
```

Provider availability, source versions and task-specific extraction requirements affect execution. See [data access](docs/DATA_ACCESS.md). Unit checks do not establish that all studies have been reproduced end to end.

## UKB preparation and readiness

Install `python -m pip install -e ".[ukb]"` and follow [the UKB workflow](docs/UKB_WORKFLOW.md). The new tools inspect exported headers, preserve paired event arrays, reject inconsistent participant keys, and record checksums and source provenance. Participant-level output must be outside this repository.

One limited Neurology_000 profile computes crude dementia outcomes. It does **not** reproduce adjusted hazard ratios or the complete paper. Other candidate field maps are preliminary; read each task’s `data/source_contract.json` and [readiness table](docs/SOURCE_READINESS.md). No task is certified for formal ranking in this release. Local scores explicitly return `formal_score_eligible: false` and `ranking_score: null`.

## Participate

Use the **Benchmark submission** issue template after this directory is hosted on GitHub. Provide your system/version, repository commit, tasks attempted, data provenance, budget and per-task results. Share participant-free artifacts through a repository or release link.

The [leaderboard](leaderboard/README.md) starts empty. Results are **self-reported** until maintainers explicitly verify them. No hosted scoring service or automatic official ranking is provided in this release.

Scores use **`local-rubric-v3-evidence`**. The scorer returns `final_score` on 0–1; multiply by 100 for display. This is a deterministic development score, not a human or LLM expert-panel score. Total score is capped by numeric coverage and target alignment. Uncertainty and sensitivity completion require [result evidence](docs/ANALYSIS_EVIDENCE.md). Read the [scoring protocol](docs/SCORING.md) before comparing systems.

Public targets and reference utilities make this an **open development benchmark**, not a secret held-out test. Disclose access to targets or reference code and keep agent execution isolated from evaluator files when claiming a blind reproduction.

## Repository contents

```text
tasks/          40 task specifications, paper metadata and public targets
src/            local scorer, workspace tools and open-data utilities
schemas/        task and submission schemas
scripts/        preparation and release-audit commands
tests/          offline structural and scoring checks
docs/           participation, scoring, data and release notes
leaderboard/    participation policy; initially no entries
```

No participant data, source-paper PDFs, provider credentials or prior experiment outputs are distributed. Original code and documentation are licensed under [MIT](LICENSE). Third-party papers and data retain their own terms; see [NOTICE.md](NOTICE.md).
