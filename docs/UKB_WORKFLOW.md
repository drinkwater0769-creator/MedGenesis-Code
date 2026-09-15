# Portable UKB workflow

## What this release supports

The tools accept CSV, TSV or Parquet exports with `eid` (or `participant.eid`). Field columns may use `53-0.0`, `f.53.0.0`, `53.0.0`, `p53_i0`, or `p53_i0_a0`. These normalize to field–instance–array coordinates. Export UKB data in your authorized environment; the repository does not download it or provide a RAP deployment.

```bash
python -m pip install -e ".[ukb]"
ccb inspect-ukb tasks/Neurology_000 --inputs "$UKB_BASELINE" "$UKB_OUTCOMES" --profile neurology000-crude-v1
ccb prepare-ukb tasks/Neurology_000 "$GOVERNED_OUTPUT/prepared" --inputs "$UKB_BASELINE" "$UKB_OUTCOMES" --profile neurology000-crude-v1 --source-release "your actual data release" --withdrawal-status not_verified
ccb validate-ukb tasks/Neurology_000 "$GOVERNED_OUTPUT/prepared"
ccb ukb-diagnostic tasks/Neurology_000 "$GOVERNED_OUTPUT/prepared" "$GOVERNED_OUTPUT/diagnostic.json"
```

Set the input variables to your own exports and `GOVERNED_OUTPUT` to a new location outside the repository. Use `--withdrawal-status applied` only if you have actually applied the relevant withdrawals. Preparation refuses existing output directories. The diagnostic refuses to overwrite existing output. Neither command sends participant data to a service.

## Input and provenance checks

- Baseline instance 0: sex 31, assessment date 53, age 21022, grip 46/47, self-reported disease 20002.
- Hospital ICD-10 41270 and matching dates 41280: retain all paired arrays. Codes and dates must share coordinates and input table.
- Death date 40000, underlying cause 40001 and contributory causes 40002: retain all registry instances together.
- Tables must contain unique, nonmissing participant keys and exactly the same participant set. No silent inner join or overlapping field ownership is allowed. Harmonize exports explicitly if their source populations differ.
- The generated local manifest records declared release and withdrawals status, contract and file hashes, and selected columns. Hash checks detect changed files; they do not certify the truth of a declaration or equivalence to a paper’s original snapshot.

Canonical header names do not convert units or code dictionaries. This profile expects standard UKB grip values in kilograms, age in years, sex coding 0/1, code 1263 for self-reported dementia, ICD-10 F00–F03 codes and valid registry dates. Check the linked UKB field documentation and the study before interpreting results. Known UKB special dates are treated as unavailable.

## Limited profile: neurology000-crude-v1

This development diagnostic requires finite positive bilateral grip, baseline age 40–80, no baseline self-reported dementia, no hospital dementia before a 730-day landmark, and survival beyond that landmark. Follow-up ends at death or 2020-06-01. Hospital events after death or follow-up end are excluded. Death causes are matched to the corresponding earliest death record. Counts below 5 are suppressed in aggregate output; this does not replace your disclosure obligations.

It produces aggregate crude incidence and dementia-mortality summaries only. It does not estimate adjusted hazard ratios, grip quintiles, interactions, or certify full paper reproduction. The 730-day implementation is explicit; historical cohort freeze and all paper details still require independent reconciliation. Diagnostic output is a private development artifact, not a complete benchmark submission or ranking result.

## Other tasks

Use `--profile ukb-candidate-input-v1` with tasks whose source contracts advertise it. This checks and projects available candidate fields only; it does not construct the paper cohort or fit its models. Missing candidates, additional cohorts, unavailable published weights, GLI transformations, and unresolved definitions are listed in each contract. Tasks with no profile fail explicitly.

Do not insert diagnostic values into unrelated target metric IDs, fabricate unavailable hazard ratios, or claim that a header check completes a task. Full submissions must meet [the submission contract](SUBMISSION.md), disclose method deviations and carry their own analysis code.
