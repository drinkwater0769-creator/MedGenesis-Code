from __future__ import annotations

import json
from pathlib import Path


REQUIRED_MANIFEST_KEYS = (
    "submission_version",
    "task_id",
    "report_path",
    "metrics_path",
    "artifacts",
)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_submission_manifest(submission_dir: str | Path) -> dict:
    root = Path(submission_dir)
    return _load_json(root / "submission.json")


def validate_submission(task_dir: str | Path, submission_dir: str | Path) -> tuple[list[str], list[str]]:
    task_root = Path(task_dir)
    submission_root = Path(submission_dir)
    errors: list[str] = []
    warnings: list[str] = []

    if not submission_root.exists():
        return [f"Submission directory does not exist: {submission_root}"], warnings

    manifest_path = submission_root / "submission.json"
    if not manifest_path.exists():
        return ["Missing required file: submission.json"], warnings

    try:
        manifest = _load_json(manifest_path)
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON in submission.json: {exc}"], warnings

    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            errors.append(f"submission.json missing key: {key}")

    task_info_path = task_root / "task_info.json"
    if task_info_path.exists():
        task_info = _load_json(task_info_path)
        expected_task_id = task_info.get("task_id")
        if expected_task_id and manifest.get("task_id") != expected_task_id:
            errors.append(
                f"submission task_id mismatch: expected {expected_task_id}, got {manifest.get('task_id')}"
            )

        for rel_path in task_info.get("deliverables", []):
            if not (submission_root / rel_path).exists():
                errors.append(f"Missing deliverable from task_info.json: {rel_path}")

    report_path = manifest.get("report_path")
    if report_path and not (submission_root / report_path).exists():
        errors.append(f"Missing report file: {report_path}")

    metrics_path = manifest.get("metrics_path")
    if metrics_path and not (submission_root / metrics_path).exists():
        errors.append(f"Missing metrics file: {metrics_path}")
    elif metrics_path:
        try:
            metrics_payload = _load_json(submission_root / metrics_path)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in metrics file {metrics_path}: {exc}")
        else:
            if "metrics" not in metrics_payload or not isinstance(metrics_payload["metrics"], dict):
                errors.append(f"Metrics file must contain an object at 'metrics': {metrics_path}")

    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict):
        errors.append("submission.json field 'artifacts' must be an object")
    else:
        for artifact_id, rel_path in artifacts.items():
            if not (submission_root / rel_path).exists():
                errors.append(f"Missing artifact '{artifact_id}': {rel_path}")

    return errors, warnings
