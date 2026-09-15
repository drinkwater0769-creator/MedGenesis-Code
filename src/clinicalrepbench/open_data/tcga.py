from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


GDC_CASES_ENDPOINT = "https://api.gdc.cancer.gov/cases"
DOWNLOAD_TIMEOUT_SECONDS = 90


def plan_downloads(manifest: dict) -> list[dict]:
    downloads: list[dict] = []
    for project_id in manifest.get("gdc_projects", []):
        downloads.append(
            {
                "provider": "tcga_gdc",
                "project_id": project_id,
                "endpoint": GDC_CASES_ENDPOINT,
                "file": f"{project_id.lower()}_cases.json",
            }
        )
    return downloads


def _project_filter(project_id: str) -> dict:
    return {
        "op": "in",
        "content": {
            "field": "project.project_id",
            "value": [project_id],
        },
    }


def download_cases(project_id: str, output_path: str | Path, fields: list[str], size: int = 20000) -> Path:
    params = {
        "filters": json.dumps(_project_filter(project_id)),
        "fields": ",".join(fields),
        "format": "JSON",
        "size": str(size),
    }
    url = f"{GDC_CASES_ENDPOINT}?{urllib.parse.urlencode(params)}"
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ClinicalRepBench-open-data-prep/0.3"},
    )
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        destination.write_bytes(response.read())
    return destination


def flatten_cases_json(path: str | Path, project_id: str) -> pd.DataFrame:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows: list[dict] = []
    for case in payload.get("data", {}).get("hits", []):
        diagnoses = case.get("diagnoses") or [{}]
        demographic = case.get("demographic") or {}
        diagnosis = diagnoses[0] if diagnoses else {}
        rows.append(
            {
                "case_id": case.get("case_id"),
                "submitter_id": case.get("submitter_id"),
                "project_id": project_id,
                "primary_diagnosis": diagnosis.get("primary_diagnosis"),
                "tumor_stage": diagnosis.get("tumor_stage"),
                "vital_status": demographic.get("vital_status"),
                "gender": demographic.get("gender"),
                "race": demographic.get("race"),
                "days_to_death": diagnosis.get("days_to_death"),
                "days_to_last_follow_up": diagnosis.get("days_to_last_follow_up"),
                "age_at_diagnosis": diagnosis.get("age_at_diagnosis"),
            }
        )
    return pd.DataFrame(rows)


def prepare_manifest(manifest: dict, workspace: str | Path, download: bool = False, cache_dir: str | Path | None = None) -> dict:
    workspace_root = Path(workspace)
    source_root = workspace_root / "data" / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    fields = manifest.get(
        "fields",
        [
            "case_id",
            "submitter_id",
            "project.project_id",
            "diagnoses.primary_diagnosis",
            "diagnoses.tumor_stage",
            "diagnoses.days_to_death",
            "diagnoses.days_to_last_follow_up",
            "diagnoses.age_at_diagnosis",
            "demographic.vital_status",
            "demographic.gender",
            "demographic.race",
        ],
    )

    frames: list[pd.DataFrame] = []
    for item in plan_downloads(manifest):
        cache_root = Path(cache_dir) if cache_dir is not None else source_root
        raw_path = cache_root / item["file"]
        if download or raw_path.exists():
            if download and not raw_path.exists():
                download_cases(item["project_id"], raw_path, fields=fields)
            frames.append(flatten_cases_json(raw_path, item["project_id"]))

    if not frames:
        raise FileNotFoundError("No GDC case JSON files found; run with download=True or stage files in data/source")

    extract = pd.concat(frames, ignore_index=True, sort=False)
    output_csv = workspace_root / "data" / "analytic_extract.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    extract.to_csv(output_csv, index=False)
    return {
        "task_id": manifest["task_id"],
        "dataset": manifest["dataset"],
        "rows": int(len(extract)),
        "output_csv": str(output_csv.resolve()),
    }
