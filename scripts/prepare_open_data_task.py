from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from clinicalrepbench.open_data.prepare import plan_open_data_task, prepare_open_data_task


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare an open-data ClinicalRepBench task.")
    parser.add_argument("task_dir")
    parser.add_argument("workspace")
    parser.add_argument("--cache-dir")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.plan_only:
        result = plan_open_data_task(args.task_dir)
    else:
        result = prepare_open_data_task(
            args.task_dir,
            args.workspace,
            cache_dir=args.cache_dir,
            download=args.download,
            force=args.force,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
