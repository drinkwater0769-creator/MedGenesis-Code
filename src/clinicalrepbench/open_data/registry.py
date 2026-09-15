from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TASKS_DIR = REPO_ROOT / "tasks"

OPEN_TASK_IDS = (
    "Cardiology_003",
    "Endocrinology_000",
    "Endocrinology_001",
    "Endocrinology_002",
    "Endocrinology_003",
    "Gastroenterology_000",
    "Gastroenterology_001",
    "Dermatology_000",
    "Immunology_000",
    "Hematology_001",
    "Neurology_002",
    "Oncology_000",
    "Oncology_001",
    "Oncology_002",
    "Oncology_003",
)


@dataclass(frozen=True)
class OpenDataTask:
    task_id: str
    task_dir: Path
    dataset: str
    provider: str
    task_info: dict
    data_manifest: dict
    source_manifest: dict


def load_json(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_source_manifest(task_dir: str | Path) -> dict:
    path = Path(task_dir) / "data" / "source_manifest.json"
    return load_json(path)


def _iter_task_dirs(tasks_dir: str | Path) -> list[Path]:
    root = Path(tasks_dir)
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "task_info.json").exists())


def discover_open_tasks(tasks_dir: str | Path = DEFAULT_TASKS_DIR) -> list[OpenDataTask]:
    tasks: list[OpenDataTask] = []
    root = Path(tasks_dir)
    task_dirs = [root / task_id for task_id in OPEN_TASK_IDS if (root / task_id / "data" / "source_manifest.json").exists()]
    if not task_dirs:
        task_dirs = _iter_task_dirs(root)

    for task_dir in task_dirs:
        source_manifest = load_source_manifest(task_dir)
        try:
            task_info = load_json(task_dir / "task_info.json")
        except OSError:
            task_info = {
                "task_id": source_manifest["task_id"],
                "primary_dataset": source_manifest["dataset"],
                "data_access": "open",
            }
        if task_info.get("data_access", "open") != "open":
            continue

        try:
            data_manifest = load_json(task_dir / "data" / "data_manifest.json")
        except OSError:
            data_manifest = {
                "task_id": source_manifest["task_id"],
                "source_dataset": source_manifest["dataset"],
                "build_status": "runnable_open_data_manifest_added",
            }
        tasks.append(
            OpenDataTask(
                task_id=source_manifest["task_id"],
                task_dir=task_dir,
                dataset=source_manifest["dataset"],
                provider=source_manifest["provider"],
                task_info=task_info,
                data_manifest=data_manifest,
                source_manifest=source_manifest,
            )
        )
    return tasks


def get_open_task(task_dir: str | Path) -> OpenDataTask:
    root = Path(task_dir)
    source_manifest = load_source_manifest(root)
    try:
        task_info = load_json(root / "task_info.json")
    except OSError:
        task_info = {
            "task_id": source_manifest["task_id"],
            "primary_dataset": source_manifest["dataset"],
            "data_access": "open",
        }
    try:
        data_manifest = load_json(root / "data" / "data_manifest.json")
    except OSError:
        data_manifest = {
            "task_id": source_manifest["task_id"],
            "source_dataset": source_manifest["dataset"],
            "build_status": "runnable_open_data_manifest_added",
        }
    return OpenDataTask(
        task_id=source_manifest["task_id"],
        task_dir=root,
        dataset=source_manifest["dataset"],
        provider=source_manifest["provider"],
        task_info=task_info,
        data_manifest=data_manifest,
        source_manifest=source_manifest,
    )
