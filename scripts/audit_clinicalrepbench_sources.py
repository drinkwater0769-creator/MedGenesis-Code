from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"
LITERATURE_MAP = TASKS / "clinicalrepbench_literature_map.json"

REQUIRED_LITERATURE_KEYS = [
    "task_id",
    "pmid",
    "title",
    "journal",
    "pubdate",
    "dataset",
    "data_access",
    "dataset_url",
    "endpoint",
    "pubmed_url",
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def audit_literature_map(errors: list[str]) -> list[dict]:
    if not LITERATURE_MAP.exists():
        errors.append("missing tasks/clinicalrepbench_literature_map.json")
        return []

    lit = load_json(LITERATURE_MAP)
    tasks = lit.get("tasks", [])
    if lit.get("task_count") != 40 or len(tasks) != 40:
        errors.append("literature map does not contain 40 tasks")

    pmids: set[str] = set()
    for item in tasks:
        task_id = item.get("task_id", "<missing-task-id>")
        for key in REQUIRED_LITERATURE_KEYS:
            if not item.get(key):
                errors.append(f"{task_id}: literature map missing {key}")

        pmid = item.get("pmid")
        if pmid in pmids:
            errors.append(f"{task_id}: duplicate PMID {pmid}")
        if pmid:
            pmids.add(pmid)


    return tasks


def audit_open_data_tasks(lit_tasks: list[dict], errors: list[str]) -> None:
    open_tasks = [task for task in lit_tasks if task.get("data_access") == "open"]
    if len(open_tasks) != 15:
        errors.append(f"expected 15 open-data tasks, found {len(open_tasks)}")

    dataset_counts: dict[str, int] = {}
    for item in open_tasks:
        task_id = item["task_id"]
        dataset_counts[item["dataset"]] = dataset_counts.get(item["dataset"], 0) + 1
        task_dir = TASKS / task_id
        source_manifest_path = task_dir / "data" / "source_manifest.json"
        data_manifest_path = task_dir / "data" / "data_manifest.json"
        metrics_path = task_dir / "target_study" / "target_metrics.json"

        for path in (source_manifest_path, data_manifest_path, metrics_path):
            if not path.exists():
                errors.append(f"{task_id}: missing {path.relative_to(task_dir)}")

        if not source_manifest_path.exists() or not data_manifest_path.exists() or not metrics_path.exists():
            continue

        source_manifest = load_json(source_manifest_path)
        data_manifest = load_json(data_manifest_path)
        target_metrics = load_json(metrics_path)

        if source_manifest.get("task_id") != task_id:
            errors.append(f"{task_id}: source_manifest task_id mismatch")
        if source_manifest.get("dataset") != item["dataset"]:
            errors.append(f"{task_id}: source_manifest dataset mismatch")
        if source_manifest.get("provider") not in {"nhanes", "tcga_gdc", "faers_openfda"}:
            errors.append(f"{task_id}: unsupported source_manifest provider {source_manifest.get('provider')}")
        if "extract" not in source_manifest:
            errors.append(f"{task_id}: source_manifest missing extract block")
        if data_manifest.get("build_status") == "source_metadata_bound; extractor script pending":
            errors.append(f"{task_id}: open-data task still marked extractor pending")
        if target_metrics.get("locked") is not True:
            errors.append(f"{task_id}: target metrics are not locked")
        if not target_metrics.get("metrics"):
            errors.append(f"{task_id}: target_metrics.json must contain metrics")

    expected_counts = {"NHANES": 10, "TCGA/GDC": 4, "FAERS": 1}
    if dataset_counts != expected_counts:
        errors.append(f"open-data dataset counts mismatch: expected {expected_counts}, found {dataset_counts}")


def main() -> int:
    errors: list[str] = []
    task_dirs = [p for p in TASKS.iterdir() if p.is_dir()]
    if len(task_dirs) != 40:
        errors.append(f"expected 40 task directories, found {len(task_dirs)}")

    lit_tasks = audit_literature_map(errors)
    audit_open_data_tasks(lit_tasks, errors)

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1

    print("OK: 40 ClinicalRepBench tasks are PubMed-bound; source contracts audited separately; 15 open-data manifests and development targets present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
