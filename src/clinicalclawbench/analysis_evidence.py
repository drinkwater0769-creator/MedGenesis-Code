"""Conservative result-backed checks. These validate evidence structure, not science."""
from __future__ import annotations

import ast
import csv
import json
import math
import re
from pathlib import Path

CHECK_KINDS = {
    "effect_uncertainty_reported": {"uncertainty"},
    "sensitivity_analysis": {"sensitivity"},
    "uncertainty_or_sensitivity": {"uncertainty", "sensitivity"},
}


def finite(value):
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def local_file(root: Path, name, suffix: str):
    if not isinstance(name, str) or Path(name).is_absolute():
        raise ValueError("Evidence paths must be relative")
    path = (root / name).resolve()
    if root.resolve() not in path.parents or not path.is_file() or path.suffix != suffix:
        raise ValueError("Missing or unsafe evidence file")
    return path


def denied(text: str, kind: str) -> bool:
    topic = (r"(?:confidence intervals?|uncertainty estimates?|standard errors?|置信区间|标准误)"
             if kind == "uncertainty" else r"(?:sensitivity analys[ie]s|robustness analys[ie]s|敏感性分析|稳健性分析)")
    # Only completion checks use this rule. Negative clinical-safety statements
    # remain valid evidence for the separate discussion/safety criteria.
    for sentence in re.split(r"[.!?。！？\n]", text.lower()):
        if (re.search(r"(?:\bno\b|without|did not|have not|not performed|not implemented|未做|没有|未完成|未进行|未计算|未估计)[^.;]{0,90}" + topic, sentence)
                or re.search(topic + r"[^.;]{0,90}(?:not (?:been )?(?:performed|implemented|computed|estimated|completed)|unavailable|未完成|未做)", sentence)):
            return True
    return False


def check_analysis_evidence(check_id: str, root: Path, report: str):
    try:
        manifest = local_file(root, "artifacts/analysis_evidence.json", ".json")
        payload = json.loads(manifest.read_text())
        if payload.get("schema_version") != "clinicalrep.analysis-evidence.v1":
            return False, "Unsupported analysis-evidence schema"
        entry = payload.get("checks", {}).get(check_id, {})
        kind = entry.get("kind")
        if entry.get("status") != "completed" or kind not in CHECK_KINDS[check_id]:
            return False, "No completed result evidence for this check"
        if denied(report, kind):
            return False, "Report explicitly declares this analysis incomplete"
        code = local_file(root, entry.get("code_path"), ".py")
        if not ast.parse(code.read_text()).body:
            return False, "Empty analysis code"
        table = local_file(root, entry.get("result_path"), ".csv")
        with table.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for row in reader:
                rows.append(row)
                if len(rows) > 10000:
                    return False, "Evidence summary exceeds 10000 rows"
        if not rows or any(not row.get("metric_id", "").strip() or not finite(row.get("estimate")) for row in rows):
            return False, "Missing metric IDs or finite effect estimates"
        if kind == "uncertainty":
            ids = [row["metric_id"] for row in rows]
            valid = len(set(ids)) == len(ids) and all(
                finite(row.get("ci_lower")) and finite(row.get("ci_upper"))
                and float(row["ci_lower"]) <= float(row["estimate"]) <= float(row["ci_upper"])
                and float(row["ci_lower"]) < float(row["ci_upper"])
                for row in rows)
        else:
            groups = {}
            valid = True
            for row in rows:
                name = row.get("analysis_id", "").strip()
                group = groups.setdefault(row["metric_id"], set())
                if not name or name in group:
                    valid = False
                group.add(name)
            valid = valid and all("primary" in group and len(group) >= 2 for group in groups.values())
        if not valid:
            return False, "Result table does not substantiate the declared analysis"
        return True, entry["result_path"] + "; result structure checked, scientific correctness unverified"
    except (OSError, ValueError, TypeError, AttributeError, KeyError, SyntaxError, UnicodeError):
        return False, "Missing, malformed or unsafe structured analysis evidence"
