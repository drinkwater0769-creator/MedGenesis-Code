"""Offline checks for the public development distribution; never print secrets."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from clinicalrepbench.validate import validate_task
from clinicalrepbench.evaluate import SCORE_PROTOCOL

IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "build", "dist"}
FORBIDDEN_DIRS = {"runs", "workspaces", "private", "raw_data", ".cache", "reference_solution"}
FORBIDDEN_SUFFIXES = {".csv", ".tsv", ".parquet", ".feather", ".xpt", ".dta", ".rds", ".pdf", ".zip", ".gz", ".log", ".pem", ".key"}
FORBIDDEN_NAMES = {"score.json", "scores.jsonl", "calibrated_scores.json", "expert_panel_scores.json", "six_dims.json", ".DS_Store"}
SENSITIVE_PATTERNS = {
    "credential-like token": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "personal absolute path": re.compile(r"/(?:Users|Volumes|home)/[^\s]+"),
    "private application identifier": re.compile(r"application\s+\d{5,}", re.I),
}


def main() -> int:
    errors = []
    files = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in IGNORED_DIRS or part.endswith(".egg-info") for part in rel.parts):
            continue
        if path.is_symlink():
            errors.append(f"symlink not allowed: {rel}")
            continue
        if not path.is_file():
            continue
        files.append(path)
        if any(part in FORBIDDEN_DIRS for part in rel.parts):
            errors.append(f"private/generated directory: {rel}")
        if (path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name in FORBIDDEN_NAMES
                or ".bak" in path.name or path.name == ".env"
                or (path.name.startswith(".env.") and path.name != ".env.example")):
            errors.append(f"excluded file type/name: {rel}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            errors.append(f"unexpected binary file: {rel}")
            continue
        for label, pattern in SENSITIVE_PATTERNS.items():
            match = pattern.search(content)
            if match:
                line = content[:match.start()].count("\n") + 1
                errors.append(f"{label}: {rel}:{line}")
        if path.suffix == ".json":
            try:
                json.loads(content)
            except ValueError:
                errors.append(f"invalid JSON: {rel}")

    infos = []
    for task in sorted((ROOT / "tasks").iterdir()):
        if not task.is_dir():
            continue
        task_errors, _ = validate_task(task)
        errors.extend(f"{task.name}: {error}" for error in task_errors)
        if (task / "task_info.json").exists():
            infos.append(json.loads((task / "task_info.json").read_text()))
    if len(infos) != 40:
        errors.append(f"expected 40 tasks; found {len(infos)}")
    domains = Counter(info["domain_code"] for info in infos)
    if len(domains) != 10 or set(domains.values()) != {4}:
        errors.append("expected 10 domains with 4 tasks each")
    access = Counter(info["data_access"] for info in infos)
    if access != {"open": 15, "credentialed": 17, "mixed": 6, "repository": 2}:
        errors.append(f"unexpected track counts: {dict(access)}")
    config = json.loads((ROOT / "benchmark_config.json").read_text())
    index = json.loads((ROOT / "tasks/clinicalrepbench_index.json").read_text())
    if config.get("score_protocol") != SCORE_PROTOCOL:
        errors.append("configured scoring protocol differs from scorer")
    if config["version"] != index["version"]:
        errors.append("configuration/task version mismatch")
    for info in infos:
        if info["data_access"] == "open":
            continue
        task = ROOT / "tasks" / info["task_id"]
        contract = json.loads((task / "data/source_contract.json").read_text())
        if contract["source_class"] != info["data_access"] or contract["task_id"] != info["task_id"]:
            errors.append(f"{task.name}: source contract mismatch")
        if contract.get("formal_score_eligible") is not False:
            errors.append(f"{task.name}: unfrozen source must not be rankable")
    if config.get("formal_score_eligible_task_ids") != []:
        errors.append("No task is certified for formal ranking in this release")
    for required in ["LICENSE", "NOTICE.md", "LICENSES/ResearchClawBench-MIT.txt"]:
        if not (ROOT / required).is_file():
            errors.append("missing release license/notice: " + required)
    for path in (ROOT / "tasks").glob("*/target_study/target_metrics.json"):
        if re.search(r"governed run|this basket|this extract|reconstruction [0-9]|reconstruction yields|reference recovers|HR anchor reproduce", path.read_text(), re.I):
            errors.append("stale internal-result narrative: " + str(path.relative_to(ROOT)))
    if "Development preview" not in (ROOT / "README.md").read_text():
        errors.append("missing development-preview homepage notice")
    source_packages = {p.name for p in (ROOT / "src").iterdir()
                       if p.is_dir() and (p / "__init__.py").is_file()}
    if source_packages != {"clinicalrepbench"}:
        errors.append("unexpected Python package in public source tree")
    if errors:
        print("\n".join("ERROR: " + error for error in errors))
        return 1
    print(f"OK: {len(files)} text files; 40 tasks / 10 domains; 15 open / 17 UKB / 6 mixed / 2 repository; no excluded files or detected secret/path patterns.")
    print("Scope: structural and pattern checks only; not an end-to-end research validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
