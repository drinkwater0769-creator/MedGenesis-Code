from __future__ import annotations

import json
import csv
import io
import tokenize
from pathlib import Path

from clinicalrepbench.submission import load_submission_manifest, validate_submission
from clinicalrepbench.reproducibility import score_reproducibility
from clinicalrepbench.analysis_evidence import CHECK_KINDS, check_analysis_evidence, finite

SCORE_PROTOCOL = "local-rubric-v3-evidence"


def load_json(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_text(path: str | Path) -> str:
    with Path(path).open("r", encoding="utf-8") as handle:
        return handle.read()


def score_metric(target_value: float, submitted_value: float, tolerance_abs: float) -> float:
    delta = abs(submitted_value - target_value)
    if delta <= tolerance_abs:
        return 1.0

    denominator = abs(target_value) + max(tolerance_abs, 1e-9)
    raw = 1.0 - (delta / denominator)
    return max(0.0, raw)


def score_metrics(target_metrics: dict, submission_metrics: dict) -> dict:
    total_weight = 0.0
    weighted_score = 0.0
    details: list[dict] = []

    submission_values = submission_metrics.get("metrics", {})
    for metric in target_metrics.get("metrics", []):
        metric_id = metric["id"]
        target_value = float(metric["value"])
        tolerance_abs = float(metric["tolerance_abs"])
        weight = float(metric["weight"])
        submitted_value = submission_values.get(metric_id)

        total_weight += weight
        if not finite(submitted_value):
            metric_score = 0.0
        else:
            metric_score = score_metric(target_value, float(submitted_value), tolerance_abs)

        weighted_score += metric_score * weight
        details.append(
            {
                "id": metric_id,
                "target": target_value,
                "submitted": submitted_value if finite(submitted_value) else None,
                "valid_numeric_submission": finite(submitted_value),
                "weight": weight,
                "score": round(metric_score, 6),
            }
        )

    objective_score = weighted_score / total_weight if total_weight else 0.0
    scoring_config = target_metrics.get("scoring", {})
    critical_metric_ids = set(scoring_config.get("critical_metric_ids", []))
    critical_miss_cap = scoring_config.get("critical_miss_cap")
    if critical_metric_ids and critical_miss_cap is not None:
        missed_critical = [
            detail["id"]
            for detail in details
            if detail["id"] in critical_metric_ids and detail["score"] < 1.0
        ]
        if missed_critical:
            objective_score = min(objective_score, float(critical_miss_cap))
    return {
        "objective_score": round(objective_score, 6),
        "details": details,
    }


def score_gate_checklist(checklist: dict, submission_dir: str | Path, manifest: dict) -> dict:
    if isinstance(checklist, list):
        return {
            "objective_score": 1.0,
            "details": [
                {
                    "id": "researchclawbench_schema",
                    "kind": "schema",
                    "required": True,
                    "evidence": "Checklist uses ResearchClawBench item scoring; gate checks are handled by submission validation.",
                    "present": True,
                }
            ],
        }

    root = Path(submission_dir)
    report_path = root / manifest["report_path"]
    report_text = load_text(report_path) if report_path.exists() else ""
    report_text_lower = report_text.lower()
    details: list[dict] = []

    required_items = [item for item in checklist.get("items", []) if item.get("required", True)]
    if not required_items:
        return {"objective_score": 1.0, "details": details}

    hits = 0
    artifacts = manifest.get("artifacts", {})
    for item in required_items:
        kind = item["kind"]
        evidence = None
        present = False

        if kind in {"table", "figure", "appendix"}:
            evidence = item.get("path") or artifacts.get(item["id"])
            if evidence is not None:
                present = (root / evidence).exists()
        elif kind == "section":
            evidence = item.get("match") or item["description"]
            present = evidence.lower() in report_text_lower

        if present:
            hits += 1

        details.append(
            {
                "id": item["id"],
                "kind": kind,
                "required": item.get("required", True),
                "evidence": evidence,
                "present": present,
            }
        )

    score = hits / len(required_items)
    return {
        "objective_score": round(score, 6),
        "details": details,
    }


def score_checklist(checklist: dict, submission_dir: str | Path, manifest: dict) -> dict:
    return score_gate_checklist(checklist, submission_dir, manifest)


def _read_optional_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _collect_artifact_text(root: Path, manifest: dict, checklist: dict) -> str:
    paths: set[str] = set()
    for value in manifest.get("artifacts", {}).values():
        if isinstance(value, str):
            paths.add(value)
    for item in checklist.get("items", []):
        path = item.get("path")
        if isinstance(path, str):
            paths.add(path)

    chunks = []
    for rel_path in sorted(paths):
        path = root / rel_path
        if path.suffix.lower() in {".csv", ".tsv", ".txt", ".md", ".svg"}:
            chunks.append(_read_optional_text(path))
    return "\n".join(chunks)


def _collect_code_text(root: Path) -> str:
    code_dir = root / "code"
    if not code_dir.exists():
        return ""
    return "\n".join(_read_optional_text(path) for path in sorted(code_dir.rglob("*.py")))


def _has_nonempty_analysis_code(root: Path) -> bool:
    return bool(_collect_code_text(root).strip())


def _contains_synthetic_or_placeholder_analysis(text: str) -> bool:
    lowered = text.lower()
    patterns = (
        "synthetic data",
        "synthetic cohort",
        "simulate synthetic",
        "simulated cohort",
        "simulated data",
        "for demonstration only",
        "for demonstration purposes",
        "replace with actual",
        "replace with the actual",
        "application xxxxx",
        "placeholder analysis",
        "dummy data",
        "mock data",
        "not estimated by model",
    )
    return any(pattern in lowered for pattern in patterns)


def _python_code_without_comments(code_text: str) -> str:
    if not code_text.strip():
        return ""
    try:
        tokens = []
        for token in tokenize.generate_tokens(io.StringIO(code_text).readline):
            if token.type == tokenize.COMMENT:
                continue
            if token.type in {tokenize.ENCODING, tokenize.ENDMARKER}:
                continue
            tokens.append(token.string)
        return " ".join(tokens)
    except tokenize.TokenError:
        return "\n".join(line.split("#", 1)[0] for line in code_text.splitlines())


def _task_source_manifest(task_root: Path) -> dict:
    path = task_root / "data" / "source_manifest.json"
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def _source_path_terms(source_manifest: dict) -> set[str]:
    terms: set[str] = set()
    extract = source_manifest.get("extract", {})
    output = extract.get("output")
    if isinstance(output, str):
        terms.add(output)
    for value in extract.get("secondary_outputs", []):
        if isinstance(value, str):
            terms.add(value)
    for component in source_manifest.get("components", []):
        if isinstance(component, dict):
            file_name = component.get("file")
            if isinstance(file_name, str):
                terms.add(file_name)
    for project in source_manifest.get("gdc_projects", []):
        if isinstance(project, str):
            terms.add(project)
    return {term for term in terms if term}


def _path_term_exists(submission_root: Path, term: str) -> bool:
    if not term or term.startswith("http"):
        return False
    relative = Path(term)
    if not relative.is_absolute() and (submission_root / relative).exists():
        return True
    name = relative.name
    if not name:
        return False
    data_root = submission_root / "data"
    if not data_root.exists():
        return False
    return any(path.name == name for path in data_root.rglob("*"))


def _uses_live_source_download(executable_code: str, source_manifest: dict) -> bool:
    lowered = executable_code.lower()
    provider = str(source_manifest.get("provider", "")).lower()
    has_network_client = any(token in lowered for token in ("requests", "urllib", "urlopen", "httpx"))
    if "tcga_gdc" in provider:
        return has_network_client and (
            "api.gdc.cancer.gov" in lowered
            or "portal.gdc.cancer.gov" in lowered
            or any(str(project).lower() in lowered for project in source_manifest.get("gdc_projects", []))
        )
    if "nhanes" in provider:
        return has_network_client and (
            "wwwn.cdc.gov" in lowered
            or ".xpt" in lowered
            or any(str(component.get("file", "")).lower() in lowered for component in source_manifest.get("components", []) if isinstance(component, dict))
        )
    if "faers" in provider:
        return has_network_client and ("api.fda.gov" in lowered or "open.fda.gov" in lowered)
    return False


def _uses_task_source_data(task_root: Path, submission_root: Path, code_text: str) -> bool:
    source_manifest = _task_source_manifest(task_root)
    if not source_manifest:
        return True
    executable_code = _python_code_without_comments(code_text)
    lowered = executable_code.lower()
    if not lowered.strip():
        return False

    source_terms = _source_path_terms(source_manifest)
    for term in source_terms:
        term_lower = term.lower()
        if term_lower in lowered and _path_term_exists(submission_root, term):
            return True

    if _uses_live_source_download(executable_code, source_manifest):
        return True

    return False


def _apply_researchclawbench_caps(
    final_score: float,
    evaluation: dict,
    metrics_score: float,
    submission_dir: str | Path,
    manifest: dict,
    task_info: dict | None = None,
    task_root: str | Path | None = None,
    reproducibility_result: dict | None = None,
) -> tuple[float, list[dict]]:
    root = Path(submission_dir)
    report_text = _read_optional_text(root / manifest.get("report_path", ""))
    code_text = _collect_code_text(root)
    combined_text = "\n".join([report_text, code_text])
    caps: list[dict] = []

    metric_floor = float(evaluation.get("metric_alignment_floor", 0.05))
    if metrics_score <= metric_floor:
        caps.append(
            {
                "id": "zero_metric_alignment_cap",
                "cap": float(evaluation.get("zero_metric_alignment_cap", 0.2)),
                "reason": "Submitted metrics do not align with hidden target metrics.",
            }
        )

    if not _has_nonempty_analysis_code(root):
        caps.append(
            {
                "id": "missing_analysis_code_cap",
                "cap": float(evaluation.get("missing_analysis_code_cap", 0.45)),
                "reason": "No executable analysis code was submitted.",
            }
        )

    if _contains_synthetic_or_placeholder_analysis(combined_text):
        caps.append(
            {
                "id": "synthetic_placeholder_analysis_cap",
                "cap": float(evaluation.get("synthetic_placeholder_analysis_cap", 0.25)),
                "reason": "Submission uses synthetic, placeholder, or demonstration-only analysis instead of source data.",
            }
        )

    if (
        task_info is not None
        and task_root is not None
        and task_info.get("data_access") == "open"
        and evaluation.get("require_source_data_use", True)
        and (
            reproducibility_result is None
            or float(reproducibility_result.get("objective_score", 0.0)) <= 0.0
        )
        and not _uses_task_source_data(Path(task_root), root, code_text)
    ):
        caps.append(
            {
                "id": "missing_source_data_use_cap",
                "cap": float(evaluation.get("missing_source_data_use_cap", 0.2)),
                "reason": (
                    "Submitted analysis code does not read the task source extract, staged source files, "
                    "or a live source-data API in executable code."
                ),
            }
        )

    if reproducibility_result is not None:
        threshold = evaluation.get("weak_reproducibility_threshold")
        cap = evaluation.get("weak_reproducibility_cap")
        if threshold is not None and cap is not None:
            reproducibility_score = float(reproducibility_result.get("objective_score", 0.0))
            if reproducibility_score < float(threshold):
                caps.append(
                    {
                        "id": "weak_reproducibility_cap",
                        "cap": float(cap),
                        "reason": (
                            "Submitted analysis code does not robustly reproduce hidden raw-data checks."
                        ),
                    }
                )

    if not caps:
        return final_score, []
    capped_score = min(final_score, *(cap["cap"] for cap in caps))
    return capped_score, caps


def _csv_row_count(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            return max(sum(1 for _ in csv.reader(handle)) - 1, 0)
    except OSError:
        return 0


def _metric_score_by_id(metric_details: list[dict]) -> dict[str, float]:
    return {detail["id"]: float(detail.get("score", 0.0)) for detail in metric_details}


def _check_terms(text: str, check: dict) -> bool:
    lowered = text.lower()
    required_all = [str(term).lower() for term in check.get("all", [])]
    required_any = [str(term).lower() for term in check.get("any", [])]
    absent = [str(term).lower() for term in check.get("absent", [])]
    if required_all and not all(term in lowered for term in required_all):
        return False
    if required_any and not any(term in lowered for term in required_any):
        return False
    if absent and any(term in lowered for term in absent):
        return False
    return True


def _score_rubric_check(check: dict, context: dict) -> tuple[bool, str | None]:
    check_type = check.get("type", "terms")
    root: Path = context["root"]
    if check.get("id") in CHECK_KINDS:
        return check_analysis_evidence(check["id"], root, context.get("report_text", ""))
    if check_type == "artifact_exists":
        rel_path = check["path"]
        return (root / rel_path).exists(), rel_path
    if check_type == "csv_min_rows":
        rel_path = check["path"]
        actual_rows = _csv_row_count(root / rel_path)
        minimum = int(check.get("min_rows", 1))
        return actual_rows >= minimum, f"{rel_path}: rows={actual_rows}, min={minimum}"
    if check_type == "metric_exact":
        metric_id = check["metric_id"]
        metric_scores = context["metric_scores"]
        return metric_scores.get(metric_id, 0.0) >= float(check.get("min_score", 1.0)), metric_id

    source = check.get("source", "report")
    source_text = context.get(f"{source}_text", "")
    if source == "any":
        source_text = "\n".join(
            [
                context.get("report_text", ""),
                context.get("code_text", ""),
                context.get("artifact_text", ""),
            ]
        )
    return _check_terms(source_text, check), source


def score_research_rubric(
    checklist: dict,
    submission_dir: str | Path,
    manifest: dict,
    metric_details: list[dict],
) -> dict:
    if isinstance(checklist, list):
        return score_researchclawbench_items(checklist, submission_dir, manifest, metric_details)

    criteria = checklist.get("rubric", {}).get("criteria", [])
    if not criteria:
        return score_gate_checklist(checklist, submission_dir, manifest)

    root = Path(submission_dir)
    report_path = root / manifest["report_path"]
    code_dir = root / "code"
    code_chunks = []
    if code_dir.exists():
        for code_path in sorted(code_dir.rglob("*.py")):
            code_chunks.append(_read_optional_text(code_path))

    context = {
        "root": root,
        "report_text": _read_optional_text(report_path),
        "code_text": "\n".join(code_chunks),
        "artifact_text": _collect_artifact_text(root, manifest, checklist),
        "metric_scores": _metric_score_by_id(metric_details),
    }
    total_weight = 0.0
    weighted_score = 0.0
    details = []
    for criterion in criteria:
        checks = criterion.get("checks", [])
        if not checks:
            continue
        check_details = []
        hits = 0.0
        critical_missed = False
        for check in checks:
            present, evidence = _score_rubric_check(check, context)
            if present:
                hits += 1.0
            elif check.get("critical"):
                critical_missed = True
            check_details.append(
                {
                    "id": check.get("id"),
                    "present": bool(present),
                    "critical": bool(check.get("critical", False)),
                    "evidence": evidence,
                }
            )
        criterion_score = hits / len(checks)
        if critical_missed and "critical_miss_cap" in criterion:
            criterion_score = min(criterion_score, float(criterion["critical_miss_cap"]))
        weight = float(criterion.get("weight", 1.0))
        total_weight += weight
        weighted_score += criterion_score * weight
        details.append(
            {
                "id": criterion["id"],
                "label": criterion.get("label", criterion["id"]),
                "weight": weight,
                "score": round(criterion_score, 6),
                "score_100": round(criterion_score * 100.0, 2),
                "checks": check_details,
            }
        )

    objective_score = weighted_score / total_weight if total_weight else 0.0
    return {
        "objective_score": round(objective_score, 6),
        "details": details,
        "scale_note": checklist.get("rubric", {}).get(
            "scale_note",
            "Rubric is normalized from criterion-level 0-100 scores.",
        ),
    }


def score_researchclawbench_items(
    items: list[dict],
    submission_dir: str | Path,
    manifest: dict,
    metric_details: list[dict],
) -> dict:
    root = Path(submission_dir)
    report_path = root / manifest["report_path"]
    code_dir = root / "code"
    code_chunks = []
    if code_dir.exists():
        for code_path in sorted(code_dir.rglob("*.py")):
            code_chunks.append(_read_optional_text(code_path))

    context = {
        "root": root,
        "report_text": _read_optional_text(report_path),
        "code_text": "\n".join(code_chunks),
        "artifact_text": _collect_artifact_text(root, manifest, {"items": items}),
        "metric_scores": _metric_score_by_id(metric_details),
    }
    total_weight = 0.0
    weighted_total = 0.0
    details = []
    for index, item in enumerate(items):
        checks = item.get("checks", [])
        if checks:
            hits = 0.0
            critical_missed = False
            check_details = []
            for check in checks:
                present, evidence = _score_rubric_check(check, context)
                if present:
                    hits += 1.0
                elif check.get("critical"):
                    critical_missed = True
                check_details.append(
                    {
                        "id": check.get("id"),
                        "present": bool(present),
                        "critical": bool(check.get("critical", False)),
                        "evidence": evidence,
                    }
                )
            item_score_100 = (hits / len(checks)) * 100.0
            if critical_missed and "critical_miss_cap" in item:
                item_score_100 = min(item_score_100, float(item["critical_miss_cap"]) * 100.0)
            reasoning = "Deterministic local judge scored checklist checks because no external ResearchClawBench LLM judge is configured."
        else:
            item_score_100 = 0.0
            check_details = []
            reasoning = "No local checks were provided for this ResearchClawBench item."
        weight = float(item.get("weight", 1.0))
        weighted_total += item_score_100 * weight
        total_weight += weight
        details.append(
            {
                "index": index,
                "id": item.get("id"),
                "type": item.get("type", "text"),
                "content": str(item.get("content", ""))[:200],
                "keywords": item.get("keywords", []),
                "weight": weight,
                "score": round(item_score_100, 2),
                "score_100": round(item_score_100, 2),
                "score_normalized": round(item_score_100 / 100.0, 6),
                "reasoning": reasoning,
                "checks": check_details,
            }
        )
    final_score_100 = weighted_total / total_weight if total_weight else 0.0
    return {
        "objective_score": round(final_score_100 / 100.0, 6),
        "final_score_100": round(final_score_100, 2),
        "details": details,
        "scale_note": (
            "ResearchClawBench-compatible scoring: each checklist item is scored 0-100 "
            "and checklist_score is the weighted average divided by 100 before final caps. "
            "No score establishes source-paper quality or human equivalence."
        ),
    }


def score_submission(task_dir: str | Path, submission_dir: str | Path) -> dict:
    errors, warnings = validate_submission(task_dir, submission_dir)
    if errors:
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "metrics_score": 0.0,
            "gate_score": 0.0,
            "checklist_score": 0.0,
            "final_score": 0.0,
            "score_protocol": SCORE_PROTOCOL,
            "formal_score_eligible": False,
            "ranking_score": None,
            "eligibility_reason": "Invalid submission; no ranking eligibility.",
        }

    task_root = Path(task_dir)
    manifest = load_submission_manifest(submission_dir)
    task_info = load_json(task_root / "task_info.json")
    target_metrics = load_json(task_root / "target_study" / "target_metrics.json")
    checklist = load_json(task_root / "target_study" / "checklist.json")
    submission_metrics = load_json(Path(submission_dir) / manifest["metrics_path"])

    metrics_result = score_metrics(target_metrics, submission_metrics)
    gate_result = score_gate_checklist(checklist, submission_dir, manifest)
    checklist_result = score_research_rubric(checklist, submission_dir, manifest, metrics_result["details"])
    reproducibility_config = target_metrics.get("reproducibility", {})
    reproducibility_enabled = bool(reproducibility_config.get("enabled"))
    reproducibility_result = None
    if reproducibility_enabled:
        reproducibility_result = score_reproducibility(task_root, submission_dir, reproducibility_config)

    evaluation = task_info.get("evaluation", {})
    metrics_weight = float(evaluation.get("metrics_weight", 0.8))
    checklist_weight = float(evaluation.get("checklist_weight", 0.2))
    gate_weight = float(evaluation.get("gate_weight", 0.0))
    reproducibility_weight = (
        float(evaluation.get("reproducibility_weight", 0.0)) if reproducibility_enabled else 0.0
    )
    weight_total = metrics_weight + checklist_weight + gate_weight + reproducibility_weight
    if weight_total <= 0:
        metrics_weight = 0.8
        checklist_weight = 0.2
        gate_weight = 0.0
        reproducibility_weight = 0.0
        weight_total = 1.0

    final_score_mode = evaluation.get("final_score_mode", "weighted_components")
    if final_score_mode == "researchclawbench_rubric":
        final_score = checklist_result["objective_score"]
    else:
        final_score = (
            metrics_result["objective_score"] * metrics_weight
            + checklist_result["objective_score"] * checklist_weight
            + gate_result["objective_score"] * gate_weight
            + (
                reproducibility_result["objective_score"] * reproducibility_weight
                if reproducibility_result is not None
                else 0.0
            )
        ) / weight_total
    if (
        final_score_mode != "researchclawbench_rubric"
        and reproducibility_result is not None
        and reproducibility_result["objective_score"] <= 0.0
    ):
        failure_cap = evaluation.get("reproducibility_failure_cap")
        if failure_cap is not None:
            final_score = min(final_score, float(failure_cap))

    researchclawbench_caps: list[dict] = []
    if final_score_mode == "researchclawbench_rubric":
        final_score, researchclawbench_caps = _apply_researchclawbench_caps(
            final_score,
            evaluation,
            metrics_result["objective_score"],
            submission_dir,
            manifest,
            task_info,
            task_root,
            reproducibility_result,
        )

    # Completeness and numeric alignment are upper bounds, not optional prose
    # points. Missing/invalid metrics remain in the original weighted denominator.
    metric_details = metrics_result["details"]
    target_weight = sum(d["weight"] for d in metric_details)
    coverage = (sum(d["weight"] for d in metric_details if d["valid_numeric_submission"])
                / target_weight if target_weight > 0 else 0.0)
    evidence_caps = [
        {"id": "numeric_metric_coverage_cap", "cap": round(coverage, 6),
         "reason": "Weighted fraction of target metrics supplied as finite values; missing metrics do not disappear from the denominator."},
        {"id": "numeric_result_alignment_cap", "cap": metrics_result["objective_score"],
         "reason": "The total score cannot exceed weighted numerical target alignment."},
    ]
    final_score = min(final_score, *(c["cap"] for c in evidence_caps))
    result = {
        "ok": True,
        "errors": errors,
        "warnings": warnings,
        "task_id": task_info["task_id"],
        "metrics_score": metrics_result["objective_score"],
        "gate_score": gate_result["objective_score"],
        "checklist_score": checklist_result["objective_score"],
        "final_score": round(final_score, 6),
        "final_score_mode": final_score_mode,
        "score_protocol": SCORE_PROTOCOL,
        "numeric_metric_coverage": round(coverage, 6),
        "evidence_caps": evidence_caps,
        "formal_score_eligible": False,
        "ranking_score": None,
        "eligibility_reason": "Development scoring only; source and method equivalence have not been certified for an official ranking.",
        "metrics": metrics_result["details"],
        "checklist": checklist_result["details"],
        "gate_checklist": gate_result["details"],
    }
    if checklist_result.get("scale_note"):
        result["checklist_scale_note"] = checklist_result["scale_note"]
    if researchclawbench_caps:
        result["researchclawbench_caps"] = researchclawbench_caps
    if reproducibility_result is not None:
        result["reproducibility_score"] = reproducibility_result["objective_score"]
        result["reproducibility"] = reproducibility_result["details"]
        result["reproducibility_errors"] = reproducibility_result.get("errors", [])
        result["reproducibility_stdout_tail"] = reproducibility_result.get("stdout_tail", "")
        result["reproducibility_stderr_tail"] = reproducibility_result.get("stderr_tail", "")
    return result
