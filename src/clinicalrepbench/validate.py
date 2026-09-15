from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FILES = (
    "agent_instructions.md",
    "task_info.json",
    "data/README.md",
    "related_work/README.md",
    "submissions/README.md",
    "target_study/checklist.json",
    "target_study/cohort_definition.sql",
    "target_study/covariates.yaml",
    "target_study/phenotype.yaml",
    "target_study/target_metrics.json",
)

REQUIRED_TASK_INFO_KEYS = (
    "task_id",
    "track",
    "domain",
    "data_access",
    "primary_question",
    "deliverables",
    "evaluation",
)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_task(task_dir: str | Path) -> tuple[list[str], list[str]]:
    root = Path(task_dir)
    errors: list[str] = []
    warnings: list[str] = []

    if not root.exists():
        return [f"Task directory does not exist: {root}"], warnings

    for rel_path in REQUIRED_FILES:
        if not (root / rel_path).exists():
            errors.append(f"Missing required file: {rel_path}")

    task_info_path = root / "task_info.json"
    if task_info_path.exists():
        try:
            task_info = _load_json(task_info_path)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in task_info.json: {exc}")
        else:
            for key in REQUIRED_TASK_INFO_KEYS:
                if key not in task_info:
                    errors.append(f"task_info.json missing key: {key}")

            evaluation = task_info.get("evaluation", {})
            objective = evaluation.get("objective_weight")
            subjective = evaluation.get("subjective_weight")
            if objective is not None and subjective is not None and objective + subjective > 1.0:
                errors.append("evaluation weights exceed 1.0 before penalties")

            metrics_weight = evaluation.get("metrics_weight")
            checklist_weight = evaluation.get("checklist_weight")
            reproducibility_weight = evaluation.get("reproducibility_weight", 0.0)
            gate_weight = evaluation.get("gate_weight", 0.0)
            if metrics_weight is not None and checklist_weight is not None:
                component_total = metrics_weight + checklist_weight + reproducibility_weight + gate_weight
                if abs(component_total - 1.0) > 1e-9:
                    errors.append(
                        "evaluation metrics_weight, checklist_weight, gate_weight, and reproducibility_weight must sum to 1.0"
                    )

    checklist_path = root / "target_study" / "checklist.json"
    if checklist_path.exists():
        try:
            checklist = _load_json(checklist_path)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in checklist.json: {exc}")
        else:
            if isinstance(checklist, list):
                if not checklist:
                    errors.append("checklist.json must contain at least one ResearchClawBench item")
                for index, item in enumerate(checklist):
                    if not isinstance(item, dict):
                        errors.append(f"Checklist item {index} must be an object")
                        continue
                    if "content" not in item:
                        errors.append(f"ResearchClawBench checklist item {index} missing content")
                    if "weight" not in item:
                        errors.append(f"ResearchClawBench checklist item {index} missing weight")
                    if item.get("type", "text") not in {"text", "image"}:
                        errors.append(f"ResearchClawBench checklist item {index} has unsupported type")
            else:
                if not checklist.get("items"):
                    errors.append("checklist.json must contain at least one checklist item")
                for item in checklist.get("items", []):
                    kind = item.get("kind")
                    if kind in {"table", "figure", "appendix"} and "path" not in item:
                        warnings.append(f"Checklist item '{item.get('id')}' has no path; scorer will use submission manifest")
                    if kind == "section" and "match" not in item:
                        warnings.append(f"Checklist section '{item.get('id')}' has no match string; scorer will use description")
                rubric = checklist.get("rubric", {})
                for criterion in rubric.get("criteria", []):
                    if "id" not in criterion:
                        errors.append("Rubric criterion missing id")
                    if not criterion.get("checks"):
                        errors.append(f"Rubric criterion '{criterion.get('id')}' must contain checks")

    metrics_path = root / "target_study" / "target_metrics.json"
    if metrics_path.exists():
        try:
            metrics = _load_json(metrics_path)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in target_metrics.json: {exc}")
        else:
            if not metrics.get("metrics"):
                errors.append("target_metrics.json must contain at least one metric")

    return errors, warnings
