from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

import pandas as pd


NHANES_DATA_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{filename}"
DOWNLOAD_TIMEOUT_SECONDS = 90


def datafile_url(year: int, filename: str) -> str:
    return NHANES_DATA_URL.format(year=year, filename=filename)


def plan_downloads(manifest: dict) -> list[dict]:
    downloads: list[dict] = []
    for component in manifest.get("components", []):
        url = component.get("url") or datafile_url(int(component["year"]), component["file"])
        downloads.append(
            {
                "provider": "nhanes",
                "component": component.get("component"),
                "cycle": component.get("cycle"),
                "file": component["file"],
                "url": url,
            }
        )
    return downloads


def download_manifest_files(manifest: dict, cache_dir: str | Path, force: bool = False) -> list[Path]:
    output_root = Path(cache_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for download in plan_downloads(manifest):
        destination = output_root / download["file"]
        if force or not destination.exists():
            request = urllib.request.Request(
                download["url"],
                headers={"User-Agent": "ClinicalClawBench-open-data-prep/0.3"},
            )
            temporary = destination.with_suffix(destination.suffix + ".part")
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                with temporary.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
            temporary.replace(destination)
        paths.append(destination)
    return paths


def _read_component(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".xpt":
        frame = pd.read_sas(path, format="xport")
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported NHANES file format: {path}")
    frame.columns = [str(column).upper() for column in frame.columns]
    return frame


def _resolve_component_file(source_dir: Path, filename: str) -> Path:
    candidates = [
        source_dir / filename,
        source_dir / filename.upper(),
        source_dir / filename.lower(),
        source_dir / Path(filename).with_suffix(".csv").name,
        source_dir / Path(filename).with_suffix(".CSV").name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Missing NHANES component {filename} in {source_dir}")


def _select_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    selected = frame.copy()
    for column in columns:
        if column not in selected.columns:
            selected[column] = pd.NA
    return selected[columns].copy()


def build_generic_extract(manifest: dict, source_dir: str | Path, output_csv: str | Path) -> tuple[pd.DataFrame, dict]:
    source_root = Path(source_dir)
    frames: list[pd.DataFrame] = []

    for component in manifest.get("components", []):
        path = _resolve_component_file(source_root, component["file"])
        columns = ["SEQN", *component.get("columns", [])]
        columns = list(dict.fromkeys(column.upper() for column in columns))
        frame = _select_columns(_read_component(path), columns)
        frame["cycle"] = component.get("cycle")
        frame["cycle_code"] = component.get("cycle_code")
        frame["component"] = component.get("component")
        frames.append(frame)

    merged: pd.DataFrame | None = None
    for frame in frames:
        component = frame.pop("component").iloc[0]
        keys = ["SEQN", "cycle", "cycle_code"]
        rename = {
            column: f"{component}_{column}"
            for column in frame.columns
            if column not in keys and column != "SEQN"
        }
        frame = frame.rename(columns=rename)
        merged = frame if merged is None else merged.merge(frame, on=keys, how="outer")

    if merged is None:
        raise ValueError("NHANES manifest has no components")

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)

    summary = {
        "task_id": manifest["task_id"],
        "dataset": "NHANES",
        "rows": int(len(merged)),
        "columns": list(merged.columns),
        "output_csv": str(output_path.resolve()),
    }
    summary_path = output_path.with_suffix(".summary.json")
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return merged, summary


def stage_downloads(manifest: dict, source_dir: str | Path, cache_dir: str | Path, force: bool = False) -> Path:
    cache_paths = download_manifest_files(manifest, cache_dir, force=force)
    source_root = Path(source_dir)
    source_root.mkdir(parents=True, exist_ok=True)
    for path in cache_paths:
        shutil.copy2(path, source_root / path.name)
    return source_root
