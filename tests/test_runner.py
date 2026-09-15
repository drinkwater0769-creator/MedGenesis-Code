import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from clinicalrepbench.runner import prepare_run, run_reference


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def build_task(root: Path) -> Path:
    task = root / "Task_000"
    (task / "data").mkdir(parents=True)
    (task / "related_work").mkdir()
    (task / "submissions").mkdir()
    (task / "target_study").mkdir()
    (task / "reference_solution").mkdir()
    (task / "agent_instructions.md").write_text("Run the reference task.\n", encoding="utf-8")
    (task / "data" / "README.md").write_text("data\n", encoding="utf-8")
    (task / "data" / "input.csv").write_text("x\n1\n", encoding="utf-8")
    (task / "related_work" / "README.md").write_text("related\n", encoding="utf-8")
    (task / "submissions" / "README.md").write_text("submissions\n", encoding="utf-8")
    (task / "target_study" / "cohort_definition.sql").write_text("-- cohort\n", encoding="utf-8")
    (task / "target_study" / "covariates.yaml").write_text("covariates: []\n", encoding="utf-8")
    (task / "target_study" / "phenotype.yaml").write_text("phenotype: demo\n", encoding="utf-8")
    write_json(
        task / "task_info.json",
        {
            "task_id": "Task_000",
            "track": "Public",
            "domain": "Demo",
            "data_access": "open",
            "primary_question": "Can the runner execute a reference solution?",
            "deliverables": [
                "submission.json",
                "report/report.md",
                "artifacts/primary_metrics.json",
                "artifacts/tables/table1.csv",
                "artifacts/figures/figure1.svg",
            ],
            "evaluation": {
                "objective_weight": 0.7,
                "subjective_weight": 0.2,
                "metrics_weight": 0.5,
                "checklist_weight": 0.5,
            },
        },
    )
    write_json(
        task / "target_study" / "checklist.json",
        {
            "items": [
                {"id": "methods", "kind": "section", "required": True, "match": "## Methods", "description": ""},
                {"id": "table1", "kind": "table", "required": True, "path": "artifacts/tables/table1.csv", "description": ""},
                {"id": "figure1", "kind": "figure", "required": True, "path": "artifacts/figures/figure1.svg", "description": ""},
            ]
        },
    )
    write_json(
        task / "target_study" / "target_metrics.json",
        {
            "metrics": [
                {"id": "cohort_n", "label": "Cohort N", "value": 1, "tolerance_abs": 0, "weight": 1}
            ]
        },
    )
    (task / "reference_solution" / "agent.py").write_text(
        textwrap.dedent(
            """
            import json
            import sys
            from pathlib import Path

            root = Path(sys.argv[1])
            (root / "report").mkdir(exist_ok=True)
            (root / "artifacts" / "tables").mkdir(parents=True, exist_ok=True)
            (root / "artifacts" / "figures").mkdir(parents=True, exist_ok=True)
            (root / "report" / "report.md").write_text("## Methods\\n", encoding="utf-8")
            (root / "artifacts" / "tables" / "table1.csv").write_text("n\\n1\\n", encoding="utf-8")
            (root / "artifacts" / "figures" / "figure1.svg").write_text("<svg/>", encoding="utf-8")
            (root / "artifacts" / "primary_metrics.json").write_text(json.dumps({"metrics": {"cohort_n": 1}}), encoding="utf-8")
            (root / "submission.json").write_text(json.dumps({
                "submission_version": "0.1",
                "task_id": "Task_000",
                "report_path": "report/report.md",
                "metrics_path": "artifacts/primary_metrics.json",
                "artifacts": {
                    "table1": "artifacts/tables/table1.csv",
                    "figure1": "artifacts/figures/figure1.svg"
                }
            }), encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    return task


class RunnerTest(unittest.TestCase):
    def test_prepare_run_copies_visible_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = build_task(Path(tmp_dir))
            run_dir = Path(tmp_dir) / "run"
            prepare_run(task, run_dir)
            self.assertTrue((run_dir / "agent_instructions.md").exists())
            self.assertTrue((run_dir / "data" / "input.csv").exists())
            self.assertFalse((run_dir / "target_study").exists())

    def test_run_reference_scores_perfectly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = build_task(Path(tmp_dir))
            run_dir = Path(tmp_dir) / "run"
            result = run_reference(task, run_dir)
            self.assertTrue(result["ok"])
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["final_score"], 1.0)
            self.assertTrue((run_dir / "score.json").exists())


if __name__ == "__main__":
    unittest.main()
