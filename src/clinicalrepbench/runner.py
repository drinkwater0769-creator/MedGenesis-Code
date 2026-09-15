from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from clinicalrepbench.evaluate import score_submission
from clinicalrepbench.validate import validate_task


VISIBLE_TASK_PATHS = (
    "agent_instructions.md",
    "task_info.json",
    "data",
    "related_work",
)


def _copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def prepare_run(task_dir: str | Path, run_dir: str | Path, force: bool = False) -> Path:
    task_root = Path(task_dir)
    run_root = Path(run_dir)

    errors, _warnings = validate_task(task_root)
    if errors:
        raise ValueError("; ".join(errors))

    if run_root.exists():
        if not force:
            raise FileExistsError(f"Run directory already exists: {run_root}")
        shutil.rmtree(run_root)

    run_root.mkdir(parents=True, exist_ok=True)
    for rel_path in VISIBLE_TASK_PATHS:
        src = task_root / rel_path
        if src.exists():
            _copy_path(src, run_root / rel_path)

    for rel_path in ("report", "artifacts/tables", "artifacts/figures"):
        (run_root / rel_path).mkdir(parents=True, exist_ok=True)

    _write_json(
        run_root / "run_metadata.json",
        {
            "task_dir": str(task_root.resolve()),
            "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    return run_root


def run_command(task_dir: str | Path, run_dir: str | Path, command: list[str], force: bool = False) -> dict:
    run_root = prepare_run(task_dir, run_dir, force=force)
    completed = subprocess.run(command, cwd=run_root, capture_output=True, text=True, check=False)

    (run_root / "run_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (run_root / "run_stderr.log").write_text(completed.stderr, encoding="utf-8")

    score = score_submission(task_dir, run_root)
    score["command"] = command
    score["returncode"] = completed.returncode
    _write_json(run_root / "score.json", score)
    return score


def run_reference(task_dir: str | Path, run_dir: str | Path, force: bool = False) -> dict:
    task_root = Path(task_dir)
    reference_script = task_root / "reference_solution" / "agent.py"
    if not reference_script.exists():
        raise FileNotFoundError(f"Missing reference solution: {reference_script}")

    command = [sys.executable, str(reference_script.resolve()), str(Path(run_dir).resolve())]
    return run_command(task_dir, run_dir, command, force=force)
