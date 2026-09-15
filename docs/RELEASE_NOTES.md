# Public development preview 0.4.2-public.4

Package: `0.4.2.dev2`. Scoring protocol remains `local-rubric-v3-evidence`.

- Removed inherited internal reconstruction numbers, local data-basket narratives and unverified reproduction claims from target explanatory notes. Numeric targets, tolerances, weights and scoring behavior are unchanged. Public reference-target provenance is retained.
- Added MIT licensing for original software/documentation and retained ResearchClawBench's upstream MIT copyright/permission notice. Dataset and paper rights remain separate.
- Marked the homepage and leaderboard policy as a development preview: trial runs and issue reports are welcome; scores are not official rankings.

## Previous releases

# Public development release 0.4.2-public.3

Package: `0.4.2.dev1`. Protocol: `local-rubric-v3-evidence`. Task/source design remains `0.4.1-source-contracts`.

- Fixed uncertainty/sensitivity completion checks that previously awarded points for negative or incomplete prose statements. These checks now require declared completed analyses, local code and numeric result tables; explicit denials fail.
- Added weighted numeric coverage and alignment upper bounds to total scores. Missing/invalid metrics remain in the denominator; unrelated extra metrics do not count.
- Reject Boolean, nonfinite and nonnumeric metric values as completion evidence. Invalid submissions now also return protocol and ranking-eligibility fields.
- Added positive and adversarial regression tests and re-scored the unchanged limited trial privately. No target values, tolerances, task weights or original trial artifacts were changed.
- This is a protocol change. Previous v2 scores require re-scoring before comparison. Evidence validation is not proof of scientific correctness; formal ranking remains disabled.

## Previous release scope

### 0.4.1-public.2

Task design: `0.4.1-source-contracts`. Package: `0.4.1.dev2`. Protocol: `local-rubric-v2-development`.

## Changes

- Corrected the old 25-UKB classification: 17 direct UKB, 6 mixed-source, 2 repository-statistics tasks; retained the 15 original open tasks.
- Added 25 source contracts with primary-source links, candidate field inventories where available and unresolved requirements. Synchronized task questions, source metadata and phenotype endpoints. Replaced misleading generic cohort SQL/covariates with explicit unfrozen status.
- Added portable UKB header inspection, governed field projection, paired-array checks, participant-key checks and checksum verification.
- Added a bounded Neurology_000 crude-outcome diagnostic, with explicit landmark, censoring, death-record pairing and limitations. It is not a complete paper-reproduction pipeline.
- Made all local scores explicitly ineligible for official ranking. Retained numeric targets and tolerances as development references; no historical scores were added.
- Retained the prior Neurology_002 open-source preparation routing correction and missing-source-data scoring-cap test.

## Distribution boundaries

No historical model scores, logs, original experiment artifacts, participant data, credentials, paper PDFs or original git history are included. Public development targets remain available to support local testing. A benchmark with public targets is not a secret held-out evaluation.

See VERIFICATION.json for executed checks. Unit tests and a local real-data diagnostic do not establish independent scientific reproduction of all 40 studies. Some source requirements and full paper methods remain unresolved. No official verified leaderboard, hosted judging service or full UKB cohort builder for all tasks is supplied.

The source snapshot originally had no project license. Release 0.4.2-public.4 adds an MIT license for original code/documentation and preserves the upstream MIT notice; third-party data and papers remain outside that grant.
