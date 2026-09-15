import json
import tempfile
import unittest
from pathlib import Path

from clinicalrepbench.evaluate import score_checklist
from clinicalrepbench.submission import validate_submission


TASK_DIR = Path(__file__).resolve().parents[1] / "tasks" / "Endocrinology_001"


class SubmissionTest(unittest.TestCase):
    def test_validate_submission_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "report").mkdir()
            (root / "artifacts" / "tables").mkdir(parents=True)
            (root / "artifacts" / "figures").mkdir(parents=True)
            (root / "report" / "report.md").write_text("## Limitations\ntext\n", encoding="utf-8")
            (root / "artifacts" / "tables" / "table1.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            (root / "artifacts" / "tables" / "table2.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            (root / "artifacts" / "figures" / "figure1.svg").write_text("<svg/>", encoding="utf-8")
            (root / "artifacts" / "primary_metrics.json").write_text(
                json.dumps({"metrics": {"cohort_n": 8102, "abd_obesity_prev_pct": 52.8665}}),
                encoding="utf-8"
            )
            (root / "submission.json").write_text(
                json.dumps(
                    {
                        "submission_version": "0.1",
                        "task_id": "Endocrinology_001",
                        "report_path": "report/report.md",
                        "metrics_path": "artifacts/primary_metrics.json",
                        "artifacts": {
                            "table1": "artifacts/tables/table1.csv",
                            "table2": "artifacts/tables/table2.csv",
                            "figure1": "artifacts/figures/figure1.svg"
                        }
                    }
                ),
                encoding="utf-8"
            )
            errors, warnings = validate_submission(TASK_DIR, root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_score_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "report").mkdir()
            (root / "artifacts" / "tables").mkdir(parents=True)
            (root / "artifacts" / "figures").mkdir(parents=True)
            (root / "report" / "report.md").write_text("## Limitations\npresent\n", encoding="utf-8")
            (root / "artifacts" / "tables" / "table1.csv").write_text("ok\n", encoding="utf-8")
            (root / "artifacts" / "figures" / "figure1.svg").write_text("<svg/>", encoding="utf-8")
            manifest = {
                "report_path": "report/report.md",
                "artifacts": {
                    "table1": "artifacts/tables/table1.csv",
                    "figure1": "artifacts/figures/figure1.svg"
                }
            }
            checklist = {
                "items": [
                    {
                        "id": "table1",
                        "kind": "table",
                        "required": True,
                        "path": "artifacts/tables/table1.csv",
                        "description": ""
                    },
                    {
                        "id": "figure1",
                        "kind": "figure",
                        "required": True,
                        "path": "artifacts/figures/figure1.svg",
                        "description": ""
                    },
                    {
                        "id": "limitations",
                        "kind": "section",
                        "required": True,
                        "match": "## Limitations",
                        "description": ""
                    }
                ]
            }
            result = score_checklist(checklist, root, manifest)
            self.assertEqual(result["objective_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
