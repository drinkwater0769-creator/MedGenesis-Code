# Scoring protocol: local-rubric-v3-evidence

This development release exposes one scoring path: `ccb score-submission TASK SUBMISSION`.

## Calculation

1. Validate the submission and collect metrics, checklist evidence and configured reproducibility checks.
2. For tasks configured with `final_score_mode = researchclawbench_rubric`, use the task's weighted checklist score as the starting score.
3. Apply task-specific caps from `task_info.json`, including metric misalignment, missing analysis code, synthetic placeholders, source-data use and weak reproducibility where configured.
4. Apply two additional upper bounds to every valid submission: weighted numeric metric coverage and weighted numeric target alignment. Missing, Boolean, nonnumeric and nonfinite metrics score zero and remain in the target denominator. Extra, non-target metric IDs do not increase coverage.
5. Return `final_score = min(score_after_existing_caps, numeric_metric_coverage, metrics_score)` on 0–1. Display it on 0–100 by multiplying by 100. `evidence_caps` reports both bounds even if another cap is lower.

The generic component weights in task metadata do **not** turn this rubric mode into a 5%/90%/5% weighted average. The executable implementation in `src/clinicalrepbench/evaluate.py` and the task-specific configuration are authoritative for this release.

The bundled checklist judge is deterministic. Discussion criteria still check declared evidence and text. The three analysis-completion checks now require structured result evidence as described below. These checks cannot independently establish scientific correctness or authentic execution. Copying target metrics is not a valid study reproduction. A reported score must be accompanied by the analysis and its provenance.

## Public targets and reproducibility fixtures

`target_study/target_metrics.json` contains **public development targets**, not historical model scores. Some targets come from paper-reported values; others were inherited from reference extraction or governance placeholders. Their provenance and tolerances are retained where possible. Public fixtures in the scorer are development checks, even if older task descriptions call them “hidden.” They are not secret once this repository is public.

Seven task targets have no numerically discriminating metric under the inherited criterion `tolerance_abs >= 10 * abs(value)` for all metrics. Their IDs are listed in `benchmark_config.json` under `numeric_boundary_tasks`. Report these separately as boundary/protocol tasks; do not interpret their target alignment as successful numerical reproduction.

This release does not include calibrated rescoring, LLM-panel services or previous scores. Do not label local results as calibrated, human-expert, or expert-panel evaluations. The documented 50-point human reference is an intended interpretation, not an empirical human comparison in this release.

## Comparing systems

- Pin the repository commit and report `local-rubric-v3-evidence`.
- Separate open, direct UKB, mixed-source and repository-statistics tasks.
- Use the same prespecified task set and disclose the public-target/reference-code access policy.
- Report every attempted task, failures, excluded/boundary tasks, coverage, data versions, runtime, token usage and cost where available.
- Compare aggregate means only over the same task set. An official track mean would require all track tasks; failures count as zero and missing tasks prevent a complete-track claim.
- Keep boundary/protocol tasks separate from the numerically scored subset, and show the denominator for each summary.

## Running submitted code

The local scorer can execute submitted analysis code for configured reproducibility checks. Its subprocess timeout is not a security sandbox. Evaluate external submissions in a separate disposable environment without private data, credentials or unrestricted access to the maintainer machine. This repository's CI does not automatically execute artifacts attached to submission issues.

## Ranking eligibility

Every local result includes `score_protocol`, `formal_score_eligible: false`, `ranking_score: null`, and an explanation. `final_score` remains a development rubric score. Passing file checks, obtaining a high rubric score, or running the limited UKB diagnostic does not make a task eligible for official ranking. Formal eligibility requires a separately frozen source/method contract and independent reproduction; none is certified in this release.

## Result-backed completion checks (v3)

`sensitivity_analysis`, `effect_uncertainty_reported`, and `uncertainty_or_sensitivity` no longer pass from report keywords. Submit `artifacts/analysis_evidence.json` using [the evidence contract](ANALYSIS_EVIDENCE.md), linking completed analyses to code and numeric result tables. Absent or malformed evidence means the check does not pass; the submission remains scorable. Explicit report denials override a completed evidence declaration. Separate clinical-safety statements such as “not actionable” continue to count for the appropriate safety discussion check.

For example, supplying four of eight equally weighted target metrics limits total score to at most 0.5; imperfect matches can lower it further. Changing the report or adding unrelated metric IDs cannot bypass this numerical upper bound. This is a transparent development scoring policy, not an empirically calibrated measure of scientific quality. Broad inherited target tolerances remain a limitation.

v3 changes the scoring protocol. Do not compare v2 and v3 scores as though they were the same evaluation; re-score the same submissions and report the version. Targets, tolerances and task weights were not changed for this fix. No historical or new real-data trial scores are distributed in the release.
