# Contributing

Report task-specification errors, data-preparation failures and scoring issues through GitHub issues. For task changes, identify the paper, changed definition, effect on targets and whether the task's version should change.

For code contributions:

```bash
python -m pip install -e ".[ukb]"
python scripts/audit_public_release.py
python -m unittest discover -s tests
```

Do not add historical model scores, execution traces, datasets, credentials or copyrighted paper files to this development distribution. Community score submissions use the dedicated issue template and participant-free artifact links.

Changes to scoring targets, tolerances, task definitions or aggregation rules must be documented and versioned. Do not silently compare scores across changed protocols.
