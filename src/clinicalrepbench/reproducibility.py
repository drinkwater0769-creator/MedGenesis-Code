from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import gzip
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_gzip_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _tcga_luad_mini_expected_metrics() -> list[dict]:
    return [
        {"id": "luad_case_n", "value": 30, "tolerance_abs": 0, "weight": 1.0},
        {"id": "sequenced_patient_n", "value": 6, "tolerance_abs": 0, "weight": 1.0},
        {"id": "non_silent_mutation_n", "value": 198, "tolerance_abs": 0, "weight": 1.0},
        {"id": "tp53_mutated_pct", "value": 16.6667, "tolerance_abs": 0.0001, "weight": 1.0},
        {"id": "kras_mutated_pct", "value": 33.3333, "tolerance_abs": 0.0001, "weight": 1.0},
        {"id": "egfr_mutated_pct", "value": 33.3333, "tolerance_abs": 0.0001, "weight": 1.0},
        {"id": "stk11_mutated_pct", "value": 16.6667, "tolerance_abs": 0.0001, "weight": 1.0},
        {"id": "keap1_mutated_pct", "value": 33.3333, "tolerance_abs": 0.0001, "weight": 1.0},
        {"id": "egfr_kras_overlap_n", "value": 1, "tolerance_abs": 0, "weight": 1.0},
        {"id": "egfr_kras_exclusive_n", "value": 2, "tolerance_abs": 0, "weight": 1.0},
        {
            "id": "egfr_kras_exclusive_pct_among_altered",
            "value": 66.6667,
            "tolerance_abs": 0.0001,
            "weight": 1.0,
        },
        {"id": "death_event_pct", "value": 33.3333, "tolerance_abs": 0.0001, "weight": 1.0},
    ]


def _build_tcga_luad_mini_fixture(workspace: Path) -> None:
    source = workspace / "data" / "source"
    sequenced_cases = [
        ("case-aa", "TCGA-AA-0001", "Alive", "stage i", "female", "white"),
        ("case-bb", "TCGA-BB-0002", "Dead", "stage ii", "male", "white"),
        ("case-cc", "TCGA-CC-0003", "Alive", "stage iii", "female", "asian"),
        ("case-dd", "TCGA-DD-0004", "Dead", "stage iv", "male", "black or african american"),
        ("case-ee", "TCGA-EE-0005", "Alive", "stage i", "female", "white"),
        ("case-ff", "TCGA-FF-0006", "Alive", "stage ii", "male", "white"),
    ]
    unsequenced_cases = [
        (f"case-ud-{index:02d}", f"TCGA-UD-{index:04d}", "Dead", "stage iii", "female", "white")
        for index in range(1, 21)
    ] + [
        (f"case-ua-{index:02d}", f"TCGA-UA-{index:04d}", "Alive", "stage i", "male", "white")
        for index in range(1, 5)
    ]
    case_hits = []
    for case_id, submitter_id, vital_status, stage, gender, race in sequenced_cases + unsequenced_cases:
        case_hits.append(
            {
                "case_id": case_id,
                "submitter_id": submitter_id,
                "diagnoses": [{"tumor_stage": stage, "days_to_death": 180.0 if vital_status == "Dead" else None}],
                "demographic": {"vital_status": vital_status, "gender": gender, "race": race},
            }
        )
    _write_json(
        source / "tcga-luad_cases.json",
        {"data": {"hits": case_hits}},
    )
    off_cohort_all_driver = [f"TCGA-ZA-{index:04d}" for index in range(1, 11)]
    off_cohort_egfr_only = [f"TCGA-ZE-{index:04d}" for index in range(1, 6)]
    off_cohort_kras_only = [f"TCGA-ZK-{index:04d}" for index in range(1, 6)]
    indexed_patients = [case[1] for case in sequenced_cases] + off_cohort_all_driver + off_cohort_egfr_only + off_cohort_kras_only
    _write_json(
        source / "tcga-luad_masked_maf_files.json",
        {
            "data": {
                "hits": [
                    {
                        "file_id": "mini-file-a",
                        "file_name": "mini_a.maf",
                        "cases": [{"submitter_id": patient} for patient in indexed_patients],
                    },
                    {
                        "file_id": "mini-file-b",
                        "file_name": "mini_b.maf.gz",
                        "cases": [{"submitter_id": patient} for patient in indexed_patients],
                    }
                ]
            }
        },
    )
    header = "\t".join(
        [
            "Hugo_Symbol",
            "Tumor_Sample_Barcode",
            "Variant_Classification",
            "Chromosome",
            "Start_Position",
            "End_Position",
            "Reference_Allele",
            "Tumor_Seq_Allele2",
        ]
    )
    rows: list[list[str]] = []

    def add_row(gene: str, patient: str, classification: str, position: int, repeats: int = 1) -> None:
        for _ in range(repeats):
            rows.append(
                [
                    gene,
                    f"{patient}-01A",
                    classification,
                    "7",
                    str(position),
                    str(position),
                    "C",
                    "T",
                ]
            )

    add_row("EGFR", "TCGA-AA-0001", "Missense_Mutation", 100, repeats=10)
    add_row("KRAS", "TCGA-BB-0002", "Missense_Mutation", 200)
    add_row("TP53", "TCGA-BB-0002", "Nonsense_Mutation", 201)
    add_row("EGFR", "TCGA-CC-0003", "Splice_Site", 300)
    add_row("KRAS", "TCGA-CC-0003", "Frame_Shift_Del", 301)
    add_row("KEAP1", "TCGA-CC-0003", "Missense_Mutation", 302)
    add_row("STK11", "TCGA-DD-0004", "Frame_Shift_Ins", 400)
    add_row("KEAP1", "TCGA-DD-0004", "Missense_Mutation", 401)
    add_row("BRAF", "TCGA-EE-0005", "Missense_Mutation", 500)
    add_row("TP53", "TCGA-FF-0006", "Silent", 600)
    add_row("KRAS", "TCGA-FF-0006", "Intron", 601)
    for patient in off_cohort_all_driver:
        for offset, gene in enumerate(["TP53", "KRAS", "EGFR", "STK11", "KEAP1"], start=1):
            add_row(gene, patient, "Missense_Mutation", 1000 + offset, repeats=3)
    for patient in off_cohort_egfr_only:
        add_row("EGFR", patient, "Missense_Mutation", 2000, repeats=3)
    for patient in off_cohort_kras_only:
        add_row("KRAS", patient, "Missense_Mutation", 3000, repeats=3)

    midpoint = len(rows) // 2
    maf_a = "\n".join([header] + ["\t".join(row) for row in rows[:midpoint]]) + "\n"
    maf_b = "\n".join([header] + ["\t".join(row) for row in rows[midpoint:]]) + "\n"
    _write_text(source / "tcga-luad_maf" / "mini_a.maf", maf_a)
    _write_gzip_text(source / "tcga-luad_maf" / "mini_b.maf.gz", maf_b)


def _score_metric(target_value: float, submitted_value: float, tolerance_abs: float) -> float:
    delta = abs(submitted_value - target_value)
    if delta <= tolerance_abs:
        return 1.0
    denominator = abs(target_value) + max(tolerance_abs, 1e-9)
    return max(0.0, 1.0 - (delta / denominator))


def _score_metrics(metrics: list[dict], submission_values: dict) -> tuple[float, list[dict]]:
    total_weight = 0.0
    weighted_score = 0.0
    details = []
    for metric in metrics:
        metric_id = metric["id"]
        target_value = float(metric["value"])
        tolerance_abs = float(metric.get("tolerance_abs", 0.0))
        weight = float(metric.get("weight", 1.0))
        submitted_value = submission_values.get(metric_id)
        total_weight += weight
        if submitted_value is None:
            metric_score = 0.0
        else:
            try:
                metric_score = _score_metric(target_value, float(submitted_value), tolerance_abs)
            except (TypeError, ValueError):
                metric_score = 0.0
        weighted_score += metric_score * weight
        details.append(
            {
                "id": metric_id,
                "target": target_value,
                "submitted": submitted_value,
                "weight": weight,
                "score": round(metric_score, 6),
            }
        )
    return (round(weighted_score / total_weight, 6) if total_weight else 0.0, details)


def _build_fixture(workspace: Path, fixture_id: str) -> list[dict]:
    if fixture_id not in {"tcga_luad_mini_raw_v1", "tcga_luad_mini_raw_v2"}:
        raise ValueError(f"Unsupported reproducibility fixture: {fixture_id}")
    _build_tcga_luad_mini_fixture(workspace)
    return _tcga_luad_mini_expected_metrics()


def _tail(text: str, max_chars: int = 2000) -> str:
    return text[-max_chars:] if len(text) > max_chars else text


def score_reproducibility(task_dir: str | Path, submission_dir: str | Path, config: dict) -> dict:
    del task_dir
    submission_root = Path(submission_dir)
    script_rel = config.get("script_path", "code/analysis.py")
    script_src = submission_root / script_rel
    if not script_src.exists():
        return {
            "objective_score": 0.0,
            "details": [],
            "errors": [f"Missing reproducible analysis script: {script_rel}"],
        }

    with tempfile.TemporaryDirectory() as tmp_dir:
        fixture_root = Path(tmp_dir)
        expected_metrics = _build_fixture(fixture_root, config.get("fixture", "tcga_luad_mini_raw_v1"))
        if config.get("expected_metrics"):
            expected_metrics = config["expected_metrics"]

        code_src = submission_root / "code"
        if code_src.exists():
            shutil.copytree(code_src, fixture_root / "code")
        else:
            (fixture_root / script_rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(script_src, fixture_root / script_rel)
        (fixture_root / "report").mkdir(parents=True, exist_ok=True)
        (fixture_root / "artifacts" / "tables").mkdir(parents=True, exist_ok=True)
        (fixture_root / "artifacts" / "figures").mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        src_root = Path(__file__).resolve().parents[1]
        env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            completed = subprocess.run(
                [sys.executable, script_rel],
                cwd=fixture_root,
                capture_output=True,
                text=True,
                timeout=int(config.get("timeout_seconds", 30)),
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "objective_score": 0.0,
                "details": [],
                "errors": [f"Analysis script timed out on hidden fixture after {exc.timeout} seconds"],
                "stdout_tail": _tail(exc.stdout or ""),
                "stderr_tail": _tail(exc.stderr or ""),
            }
        if completed.returncode != 0:
            return {
                "objective_score": 0.0,
                "details": [],
                "errors": [f"Analysis script failed on hidden fixture with exit code {completed.returncode}"],
                "stdout_tail": _tail(completed.stdout),
                "stderr_tail": _tail(completed.stderr),
            }

        metrics_path = fixture_root / config.get("metrics_path", "artifacts/primary_metrics.json")
        if not metrics_path.exists():
            return {
                "objective_score": 0.0,
                "details": [],
                "errors": [f"Analysis script did not write {metrics_path.relative_to(fixture_root)}"],
                "stdout_tail": _tail(completed.stdout),
                "stderr_tail": _tail(completed.stderr),
            }
        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "objective_score": 0.0,
                "details": [],
                "errors": [f"Invalid reproducibility metrics JSON: {exc}"],
                "stdout_tail": _tail(completed.stdout),
                "stderr_tail": _tail(completed.stderr),
            }

        score, details = _score_metrics(expected_metrics, payload.get("metrics", {}))
        return {
            "objective_score": score,
            "details": details,
            "errors": [],
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        }
