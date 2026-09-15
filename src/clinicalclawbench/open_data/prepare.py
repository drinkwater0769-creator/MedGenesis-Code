from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pandas as pd

from clinicalclawbench.open_data.registry import get_open_task, load_json, load_source_manifest
from . import faers, nhanes, tcga, tcga_luad


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def plan_open_data_task(task_dir: str | Path) -> dict:
    task = get_open_task(task_dir)
    manifest = task.source_manifest
    if task.provider == "nhanes":
        downloads = nhanes.plan_downloads(manifest)
    elif task.provider == "tcga_gdc":
        if manifest.get("extract", {}).get("analysis") == "tcga_luad_molecular_profile":
            downloads = tcga_luad.plan_downloads(manifest)
        else:
            downloads = tcga.plan_downloads(manifest)
    elif task.provider == "faers_openfda":
        downloads = faers.plan_downloads(manifest)
    else:
        raise ValueError(f"Unsupported open-data provider: {task.provider}")

    return {
        "task_id": task.task_id,
        "dataset": task.dataset,
        "provider": task.provider,
        "downloads": downloads,
        "extract": manifest.get("extract", {}),
    }


def prepare_open_data_task(
    task_dir: str | Path,
    workspace: str | Path,
    cache_dir: str | Path | None = None,
    download: bool = False,
    force: bool = False,
) -> dict:
    task = get_open_task(task_dir)
    manifest = task.source_manifest
    workspace_root = Path(workspace)
    source_dir = workspace_root / "data" / "source"
    output_csv = workspace_root / "data" / "analytic_extract.csv"

    if output_csv.exists() and not force:
        existing = pd.read_csv(output_csv)
        return {
            "task_id": task.task_id,
            "dataset": task.dataset,
            "provider": task.provider,
            "rows": int(len(existing)),
            "output_csv": str(output_csv.resolve()),
            "reused_existing_extract": True,
        }

    if manifest.get("extract", {}).get("analysis") == "nhanes_periodontitis_depression_mortality":
        from clinicalclawbench.public_nhanes_neuro_002 import build_extract

        cache_root = Path(cache_dir) if cache_dir else source_dir
        if download:
            nhanes.download_manifest_files(manifest, cache_root)
        for component in manifest.get("components", []):
            name = component["file"]
            if component.get("component") == "NHANES_III" or name.startswith("NHANES_III_MORT"):
                destination = cache_root / "nhanes3" / name
            elif component.get("component") == "LMF":
                destination = cache_root / "lmf" / name
            else:
                destination = cache_root / name
            source = cache_root / name
            if not destination.is_file() and source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            if not destination.is_file() or destination.stat().st_size == 0:
                raise FileNotFoundError(f"Missing Neurology_002 source file {name}; stage the declared files or use --download.")
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        analytic, summary = build_extract(
            cache_root, cache_root / "nhanes3", cache_root / "lmf", output_csv,
            workspace_root / "data" / "cohort_summary.json",
        )
        return {
            "task_id": task.task_id,
            "dataset": task.dataset,
            "provider": task.provider,
            "rows": int(len(analytic)),
            "output_csv": str(output_csv.resolve()),
            "summary": summary,
        }

    if manifest.get("extract", {}).get("analysis") == "nhanes3_sle_lycopene_mortality":
        from clinicalclawbench.public_nhanes3_immu_000 import build_extract as build_i000_extract

        analytic, summary = build_i000_extract(
            cache_dir or source_dir,
            output_csv,
            workspace_root / "data" / "cohort_summary.json",
        )
        return {
            "task_id": task.task_id,
            "dataset": task.dataset,
            "provider": task.provider,
            "rows": int(len(analytic)),
            "output_csv": str(output_csv.resolve()),
            "summary": summary,
        }

    if manifest.get("extract", {}).get("analysis") == "nhanes3_gallstone_nafld_mortality":
        from clinicalclawbench.public_nhanes3_gastro_001 import build_extract as build_g001_extract

        analytic, summary = build_g001_extract(
            cache_dir or source_dir,
            output_csv,
            workspace_root / "data" / "cohort_summary.json",
        )
        return {
            "task_id": task.task_id,
            "dataset": task.dataset,
            "provider": task.provider,
            "rows": int(len(analytic)),
            "output_csv": str(output_csv.resolve()),
            "summary": summary,
        }

    if manifest.get("extract", {}).get("analysis") == "nhanes3_thyroid_mafld_mortality":
        from clinicalclawbench.public_nhanes3_endo_002 import build_extract as build_endo002_extract

        analytic, summary = build_endo002_extract(
            cache_dir or source_dir,
            output_csv,
            workspace_root / "data" / "cohort_summary.json",
        )
        return {
            "task_id": task.task_id,
            "dataset": task.dataset,
            "provider": task.provider,
            "rows": int(len(analytic)),
            "output_csv": str(output_csv.resolve()),
            "summary": summary,
        }

    if manifest.get("extract", {}).get("analysis") == "nhanes3_tyg_nafld_mortality":
        from clinicalclawbench.public_nhanes3_gastro_000 import build_extract

        analytic, summary = build_extract(
            cache_dir or source_dir,
            output_csv,
            workspace_root / "data" / "cohort_summary.json",
        )
        return {
            "task_id": task.task_id,
            "dataset": task.dataset,
            "provider": task.provider,
            "rows": int(len(analytic)),
            "output_csv": str(output_csv.resolve()),
            "summary": summary,
        }

    if task.provider == "nhanes":
        if download:
            nhanes.stage_downloads(
                manifest,
                source_dir=source_dir,
                cache_dir=cache_dir or source_dir,
                force=force,
            )

        if manifest.get("extract", {}).get("analysis") == "nhanes_ckd_anemia_hyperuricemia_mortality":
            from clinicalclawbench.public_nhanes_hematology_001_prep import prepare_public_nhanes_hema001_extract

            analytic, summary = prepare_public_nhanes_hema001_extract(
                input_dir=source_dir,
                output_csv=output_csv,
                output_summary_json=workspace_root / "data" / "cohort_summary.json",
                manifest_path=Path(task_dir) / "data" / "source_manifest.json",
                lmf_cache_dir=(Path(cache_dir) / "lmf") if cache_dir else None,
                download_lmf=True,
            )
            return {
                "task_id": task.task_id,
                "dataset": task.dataset,
                "provider": task.provider,
                "rows": int(len(analytic)),
                "output_csv": str(output_csv.resolve()),
                "summary": summary,
            }

        if manifest.get("extract", {}).get("analysis") == "nhanes_bp_cvd_mortality_sex":
            from clinicalclawbench.public_nhanes_cardiology_003_prep import prepare_public_nhanes_cardio003_extract

            analytic, summary = prepare_public_nhanes_cardio003_extract(
                input_dir=source_dir,
                output_csv=output_csv,
                output_summary_json=workspace_root / "data" / "cohort_summary.json",
                manifest_path=Path(task_dir) / "data" / "source_manifest.json",
                lmf_cache_dir=(Path(cache_dir) / "lmf") if cache_dir else None,
                download_lmf=True,
            )
            return {
                "task_id": task.task_id,
                "dataset": task.dataset,
                "provider": task.provider,
                "rows": int(len(analytic)),
                "output_csv": str(output_csv.resolve()),
                "summary": summary,
            }

        if manifest.get("extract", {}).get("analysis") == "nhanes_crm_overlap":
            from clinicalclawbench.public_nhanes_003_prep import prepare_public_nhanes_003_extract

            analytic, summary = prepare_public_nhanes_003_extract(
                input_dir=source_dir,
                output_csv=output_csv,
                output_summary_json=workspace_root / "data" / "cohort_summary.json",
                manifest_path=Path(task_dir) / "data" / "source_manifest.json",
            )
            return {
                "task_id": task.task_id,
                "dataset": task.dataset,
                "provider": task.provider,
                "rows": int(len(analytic)),
                "output_csv": str(output_csv.resolve()),
                "summary": summary,
            }

        if manifest.get("extract", {}).get("analysis") == "nhanes_abdominal_obesity_hypertension":
            from clinicalclawbench.public_nhanes_001_prep import prepare_public_nhanes_001_extract

            analytic, summary = prepare_public_nhanes_001_extract(
                input_dir=source_dir,
                output_csv=output_csv,
                output_summary_json=workspace_root / "data" / "cohort_summary.json",
                manifest_path=Path(task_dir) / "data" / "source_manifest.json",
            )
            return {
                "task_id": task.task_id,
                "dataset": task.dataset,
                "provider": task.provider,
                "rows": int(len(analytic)),
                "output_csv": str(output_csv.resolve()),
                "summary": summary,
            }

        extract, summary = nhanes.build_generic_extract(manifest, source_dir, output_csv)
        return {
            "task_id": task.task_id,
            "dataset": task.dataset,
            "provider": task.provider,
            "rows": int(len(extract)),
            "output_csv": str(output_csv.resolve()),
            "summary": summary,
        }

    if task.provider == "tcga_gdc":
        if manifest.get("extract", {}).get("analysis") == "tcga_project_profile":
            from clinicalclawbench.open_data.tcga_project import prepare_project_profile

            return prepare_project_profile(
                manifest, workspace_root, cache_dir=cache_dir, download=download, force=force)
        if manifest.get("extract", {}).get("analysis") == "tcga_luad_molecular_profile":
            return tcga_luad.prepare_luad_molecular_profile(
                manifest,
                workspace_root,
                cache_dir=cache_dir,
                download=download,
                force=force,
            )
        result = tcga.prepare_manifest(manifest, workspace_root, download=download, cache_dir=cache_dir)
        result["provider"] = task.provider
        return result

    if task.provider == "faers_openfda":
        result = faers.prepare_manifest(manifest, workspace_root, download=download, cache_dir=cache_dir)
        result["provider"] = task.provider
        return result

    raise ValueError(f"Unsupported open-data provider: {task.provider}")


def _safe_pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return math.nan
    return round(float(numerator / denominator * 100.0), 4)


def _generic_metrics(frame: pd.DataFrame) -> dict:
    rows = int(len(frame))
    cols = int(len(frame.columns))
    missing_cells = int(frame.isna().sum().sum())
    total_cells = max(rows * cols, 1)
    metrics = {
        "cohort_n": rows,
        "analysis_column_count": cols,
        "missing_cell_pct": _safe_pct(missing_cells, total_cells),
    }

    if "vital_status" in frame.columns:
        metrics["death_event_pct"] = _safe_pct(frame["vital_status"].astype(str).str.lower().eq("dead").sum(), rows)
    if "serious" in frame.columns:
        metrics["serious_report_pct"] = _safe_pct(pd.to_numeric(frame["serious"], errors="coerce").eq(1).sum(), rows)
    return metrics


def write_generic_reference_submission(task_dir: str | Path, workspace: str | Path) -> dict:
    task_root = Path(task_dir)
    workspace_root = Path(workspace)
    task_info = load_json(task_root / "task_info.json")
    extract = pd.read_csv(workspace_root / "data" / "analytic_extract.csv")
    metrics = _generic_metrics(extract)

    artifacts = workspace_root / "artifacts"
    table_dir = artifacts / "tables"
    figure_dir = artifacts / "figures"
    report_dir = workspace_root / "report"
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame([metrics]).to_csv(table_dir / "table1.csv", index=False)
    pd.DataFrame({"column": extract.columns, "missing_n": extract.isna().sum().values}).to_csv(table_dir / "table2.csv", index=False)
    (figure_dir / "figure1.svg").write_text(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"640\" height=\"120\">"
        "<rect width=\"640\" height=\"120\" fill=\"white\"/>"
        "<text x=\"24\" y=\"68\" font-family=\"Arial\" font-size=\"22\">Open-data extract generated</text>"
        "</svg>\n",
        encoding="utf-8",
    )
    _write_json(artifacts / "primary_metrics.json", {"metrics": metrics})

    report = f"""# Open-Data Reference Report

## Methods

This reference run prepared the official open dataset declared for `{task_info['task_id']}` and generated the task analytic extract using the bundled source manifest.

## Re-Discovery

The run records the cohort size and core extract completeness needed to reproduce the source-study workflow.

## New-Discovery

The generated extract can be extended with task-specific subgroup or sensitivity analyses once target article-specific estimands are adjudicated.

## Limitations

This generic reference records data availability and extract integrity. Task-specific inferential estimates should be locked with `scripts/lock_open_data_target_metrics.py` after the governed reference run.

## Clinical Safety

The output is a benchmark artifact, not a clinical decision tool, and should not be interpreted as causal or actionable patient-level evidence.
"""
    (report_dir / "report.md").write_text(report, encoding="utf-8")
    _write_json(
        workspace_root / "submission.json",
        {
            "submission_version": "0.1",
            "task_id": task_info["task_id"],
            "report_path": "report/report.md",
            "metrics_path": "artifacts/primary_metrics.json",
            "artifacts": {
                "table1": "artifacts/tables/table1.csv",
                "table2": "artifacts/tables/table2.csv",
                "figure1": "artifacts/figures/figure1.svg",
            },
        },
    )
    return metrics


def run_open_data_reference(
    task_dir: str | Path,
    workspace: str | Path,
    cache_dir: str | Path | None = None,
    download: bool = False,
    force: bool = False,
) -> dict:
    task = get_open_task(task_dir)
    prepare_open_data_task(task.task_dir, workspace, cache_dir=cache_dir, download=download, force=force)

    if task.task_id == "Endocrinology_001":
        from clinicalclawbench.public_nhanes_001_reference import run_public_nhanes_001_reference

        return run_public_nhanes_001_reference(workspace)
    if task.source_manifest.get("extract", {}).get("analysis") == "nhanes_crm_overlap":
        from clinicalclawbench.public_nhanes_003_reference import run_public_nhanes_003_reference

        return run_public_nhanes_003_reference(workspace)
    if task.source_manifest.get("extract", {}).get("analysis") == "nhanes_bp_cvd_mortality_sex":
        from clinicalclawbench.public_nhanes_cardiology_003_reference import run_public_nhanes_cardio003_reference

        return run_public_nhanes_cardio003_reference(workspace)
    if task.source_manifest.get("extract", {}).get("analysis") == "nhanes_ckd_anemia_hyperuricemia_mortality":
        from clinicalclawbench.public_nhanes_hematology_001_reference import run_public_nhanes_hema001_reference

        return run_public_nhanes_hema001_reference(workspace)
    if task.source_manifest.get("extract", {}).get("analysis") == "nhanes3_tyg_nafld_mortality":
        from clinicalclawbench.public_nhanes3_gastro_000 import run_reference as run_gastro000_reference

        return run_gastro000_reference(workspace, cache_dir=cache_dir)
    if task.source_manifest.get("extract", {}).get("analysis") == "nhanes3_thyroid_mafld_mortality":
        from clinicalclawbench.public_nhanes3_endo_002 import run_reference as run_endo002_reference

        return run_endo002_reference(workspace, cache_dir=cache_dir)
    if task.source_manifest.get("extract", {}).get("analysis") == "nhanes3_gallstone_nafld_mortality":
        from clinicalclawbench.public_nhanes3_gastro_001 import run_reference as run_g001_reference

        return run_g001_reference(workspace, cache_dir=cache_dir)
    if task.source_manifest.get("extract", {}).get("analysis") == "nhanes3_sle_lycopene_mortality":
        from clinicalclawbench.public_nhanes3_immu_000 import run_reference as run_i000_reference

        return run_i000_reference(workspace, cache_dir=cache_dir)
    if task.source_manifest.get("extract", {}).get("analysis") == "tcga_project_profile":
        from clinicalclawbench.open_data.tcga_project import prepare_project_profile

        result = prepare_project_profile(task.source_manifest, Path(workspace),
                                         cache_dir=cache_dir, download=download, force=force)
        return result["metrics"]
    if task.task_id == "Oncology_000" and task.source_manifest.get("extract", {}).get("analysis") == "tcga_luad_molecular_profile":
        return tcga_luad.run_luad_reference(
            task.source_manifest,
            workspace,
            cache_dir=cache_dir,
            download=download,
            force=force,
        )
    return write_generic_reference_submission(task.task_dir, workspace)


def lock_target_metrics_from_submission(
    task_dir: str | Path,
    submission_metrics_path: str | Path,
    output_path: str | Path | None = None,
) -> dict:
    task_root = Path(task_dir)
    metrics_payload = load_json(submission_metrics_path)
    submitted = metrics_payload.get("metrics", {})
    existing = load_json(task_root / "target_study" / "target_metrics.json")
    existing_by_id = {metric["id"]: metric for metric in existing.get("metrics", [])}

    locked_metrics = []
    for metric_id, value in submitted.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        previous = existing_by_id.get(metric_id, {})
        locked_metrics.append(
            {
                "id": metric_id,
                "label": previous.get("label", metric_id.replace("_", " ").title()),
                "value": float(value),
                "tolerance_abs": float(previous.get("tolerance_abs", max(abs(float(value)) * 0.05, 1.0))),
                "weight": float(previous.get("weight", 1.0)),
                "direction": "target_match",
                "notes": "Locked from the bundled open-data reference run.",
            }
        )

    payload = {
        "scale_note": "Numeric target metrics are locked from the bundled open-data reference run and scored by absolute tolerance.",
        "locked": True,
        "source": "open_data_reference_submission",
        "metrics": locked_metrics,
    }
    destination = Path(output_path) if output_path is not None else task_root / "target_study" / "target_metrics.json"
    _write_json(destination, payload)
    return payload
