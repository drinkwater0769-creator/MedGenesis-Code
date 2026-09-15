from __future__ import annotations

import argparse
import json
import sys

from clinicalrepbench.evaluate import load_json, score_metrics, score_submission
from clinicalrepbench.open_data.prepare import (
    lock_target_metrics_from_submission,
    plan_open_data_task,
    prepare_open_data_task,
)
from clinicalrepbench.runner import prepare_run, run_command, run_reference
from clinicalrepbench.submission import validate_submission
from clinicalrepbench.validate import validate_task


def _cmd_validate_task(args: argparse.Namespace) -> int:
    errors, warnings = validate_task(args.task_dir)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        return 1

    print(f"OK: task structure looks valid for {args.task_dir}")
    return 0


def _cmd_score_metrics(args: argparse.Namespace) -> int:
    target_metrics = load_json(args.target_metrics)
    submission_metrics = load_json(args.submission_metrics)
    result = score_metrics(target_metrics, submission_metrics)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _cmd_validate_submission(args: argparse.Namespace) -> int:
    errors, warnings = validate_submission(args.task_dir, args.submission_dir)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        return 1

    print(f"OK: submission looks valid for {args.submission_dir}")
    return 0


def _cmd_score_submission(args: argparse.Namespace) -> int:
    result = score_submission(args.task_dir, args.submission_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


def _cmd_prepare_run(args: argparse.Namespace) -> int:
    run_root = prepare_run(args.task_dir, args.run_dir, force=args.force)
    print(f"Prepared run workspace at {run_root}")
    return 0


def _cmd_run_task(args: argparse.Namespace) -> int:
    if not args.command:
        print("ERROR: missing command after '--'")
        return 2

    result = run_command(args.task_dir, args.run_dir, args.command, force=args.force)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("returncode") == 0 and result.get("ok") else 1


def _cmd_run_reference(args: argparse.Namespace) -> int:
    result = run_reference(args.task_dir, args.run_dir, force=args.force)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("returncode") == 0 and result.get("ok") else 1


def _cmd_plan_open_data(args: argparse.Namespace) -> int:
    print(json.dumps(plan_open_data_task(args.task_dir), indent=2, sort_keys=True))
    return 0


def _cmd_prepare_open_data(args: argparse.Namespace) -> int:
    result = prepare_open_data_task(
        args.task_dir,
        args.workspace,
        cache_dir=args.cache_dir,
        download=args.download,
        force=args.force,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _cmd_lock_target_metrics(args: argparse.Namespace) -> int:
    result = lock_target_metrics_from_submission(
        args.task_dir,
        args.submission_metrics,
        output_path=args.output_path,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_ukb = subparsers.add_parser("inspect-ukb", help="Inspect source headers without reading participant rows.")
    inspect_ukb.add_argument("task_dir")
    inspect_ukb.add_argument("--inputs", nargs="+", required=True)
    inspect_ukb.add_argument("--profile", default="ukb-candidate-input-v1")
    inspect_ukb.set_defaults(func=_cmd_inspect_ukb)

    prepare_ukb = subparsers.add_parser("prepare-ukb", help="Prepare a governed local field projection; never place outputs in the public repo.")
    prepare_ukb.add_argument("task_dir")
    prepare_ukb.add_argument("output")
    prepare_ukb.add_argument("--inputs", nargs="+", required=True)
    prepare_ukb.add_argument("--profile", default="ukb-candidate-input-v1")
    prepare_ukb.add_argument("--source-release", required=True)
    prepare_ukb.add_argument("--withdrawal-status", required=True, choices=["applied", "not_verified"])
    prepare_ukb.add_argument("--chunksize", type=int, default=5000)
    prepare_ukb.set_defaults(func=_cmd_prepare_ukb)

    validate_ukb = subparsers.add_parser("validate-ukb", help="Check prepared input hashes and task/contract binding.")
    validate_ukb.add_argument("task_dir")
    validate_ukb.add_argument("prepared")
    validate_ukb.set_defaults(func=_cmd_validate_ukb)

    diagnostic = subparsers.add_parser("ukb-diagnostic", help="Run the named Neurology_000 crude development profile.")
    diagnostic.add_argument("task_dir")
    diagnostic.add_argument("prepared")
    diagnostic.add_argument("output")
    diagnostic.add_argument("--chunksize", type=int, default=5000)
    diagnostic.set_defaults(func=_cmd_ukb_diagnostic)

    validate_parser = subparsers.add_parser("validate-task", help="Validate a task directory.")
    validate_parser.add_argument("task_dir")
    validate_parser.set_defaults(func=_cmd_validate_task)

    score_parser = subparsers.add_parser(
        "score-metrics",
        help="Score a submission metrics JSON against target metrics JSON.",
    )
    score_parser.add_argument("target_metrics")
    score_parser.add_argument("submission_metrics")
    score_parser.set_defaults(func=_cmd_score_metrics)

    validate_submission_parser = subparsers.add_parser(
        "validate-submission",
        help="Validate a submission directory against a task.",
    )
    validate_submission_parser.add_argument("task_dir")
    validate_submission_parser.add_argument("submission_dir")
    validate_submission_parser.set_defaults(func=_cmd_validate_submission)

    score_submission_parser = subparsers.add_parser(
        "score-submission",
        help="Score a submission directory against a task.",
    )
    score_submission_parser.add_argument("task_dir")
    score_submission_parser.add_argument("submission_dir")
    score_submission_parser.set_defaults(func=_cmd_score_submission)

    prepare_parser = subparsers.add_parser("prepare-run", help="Prepare a run workspace for a task.")
    prepare_parser.add_argument("task_dir")
    prepare_parser.add_argument("run_dir")
    prepare_parser.add_argument("--force", action="store_true")
    prepare_parser.set_defaults(func=_cmd_prepare_run)

    run_parser = subparsers.add_parser("run-task", help="Prepare, execute, and score a task run.")
    run_parser.add_argument("task_dir")
    run_parser.add_argument("run_dir")
    run_parser.add_argument("--force", action="store_true")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    run_parser.set_defaults(func=_cmd_run_task)

    reference_parser = subparsers.add_parser(
        "run-reference",
        help="Run the task's bundled reference solution and score it.",
    )
    reference_parser.add_argument("task_dir")
    reference_parser.add_argument("run_dir")
    reference_parser.add_argument("--force", action="store_true")
    reference_parser.set_defaults(func=_cmd_run_reference)

    plan_open_parser = subparsers.add_parser("plan-open-data", help="Print open-data downloads and extract plan.")
    plan_open_parser.add_argument("task_dir")
    plan_open_parser.set_defaults(func=_cmd_plan_open_data)

    prepare_open_parser = subparsers.add_parser("prepare-open-data", help="Download/stage and extract an open-data task.")
    prepare_open_parser.add_argument("task_dir")
    prepare_open_parser.add_argument("workspace")
    prepare_open_parser.add_argument("--cache-dir")
    prepare_open_parser.add_argument("--download", action="store_true")
    prepare_open_parser.add_argument("--force", action="store_true")
    prepare_open_parser.set_defaults(func=_cmd_prepare_open_data)

    lock_parser = subparsers.add_parser("lock-target-metrics", help="Lock target metrics from a reference metrics JSON.")
    lock_parser.add_argument("task_dir")
    lock_parser.add_argument("submission_metrics")
    lock_parser.add_argument("--output-path")
    lock_parser.set_defaults(func=_cmd_lock_target_metrics)

    return parser


def _cmd_inspect_ukb(args: argparse.Namespace) -> int:
    from clinicalrepbench.ukb_io import inspect_inputs
    result = inspect_inputs(args.task_dir, args.inputs, args.profile)
    print(json.dumps(result, indent=2))
    return 0 if result["input_headers_ok"] else 2


def _cmd_prepare_ukb(args: argparse.Namespace) -> int:
    from clinicalrepbench.ukb_io import prepare_inputs
    result = prepare_inputs(args.task_dir, args.inputs, args.output, args.profile,
                            args.source_release, args.withdrawal_status, args.chunksize)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_validate_ukb(args: argparse.Namespace) -> int:
    from clinicalrepbench.ukb_io import verify_prepared
    result = verify_prepared(args.prepared, args.task_dir)
    result.pop("provenance", None)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


def _cmd_ukb_diagnostic(args: argparse.Namespace) -> int:
    from clinicalrepbench.ukb_diagnostic import run_neurology_diagnostic
    print(json.dumps(run_neurology_diagnostic(args.prepared, args.task_dir, args.output, args.chunksize), indent=2))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
