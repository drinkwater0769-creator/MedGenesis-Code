import json
import tempfile
import unittest
from pathlib import Path

from clinicalrepbench.evaluate import score_submission


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"

CALIBRATION_WEIGHT_KEYS = {
    "metrics_weight": 0.05,
    "checklist_weight": 0.9,
    "gate_weight": 0.05,
    "reproducibility_weight": 0.0,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def exact_target_metrics(task_dir: Path) -> dict:
    target = load_json(task_dir / "target_study" / "target_metrics.json")
    return {metric["id"]: metric["value"] for metric in target["metrics"]}


def write_static_submission(task_dir: Path, root: Path) -> None:
    (root / "report").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "tables").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "figures").mkdir(parents=True, exist_ok=True)
    (root / "report" / "report.md").write_text(
        "\n".join(
            [
                "# Static ClinicalRepBench Submission",
                "",
                "## Methods",
                "Static report.",
                "",
                "## Re-Discovery",
                "Static report.",
                "",
                "## New-Discovery",
                "Static report.",
                "",
                "## Results",
                "Static report.",
                "",
                "## Limitations",
                "Static report.",
                "",
                "## Clinical Safety",
                "Static report.",
            ]
        ),
        encoding="utf-8",
    )
    (root / "artifacts" / "tables" / "table1.csv").write_text("measure,value\nn,1\n", encoding="utf-8")
    (root / "artifacts" / "tables" / "table2.csv").write_text("measure,value\nn,1\n", encoding="utf-8")
    (root / "artifacts" / "figures" / "figure1.svg").write_text("<svg/>", encoding="utf-8")
    write_json(root / "artifacts" / "primary_metrics.json", {"metrics": exact_target_metrics(task_dir)})
    write_json(
        root / "submission.json",
        {
            "submission_version": "0.1",
            "task_id": task_dir.name,
            "report_path": "report/report.md",
            "metrics_path": "artifacts/primary_metrics.json",
            "artifacts": {
                "table1": "artifacts/tables/table1.csv",
                "table2": "artifacts/tables/table2.csv",
                "figure1": "artifacts/figures/figure1.svg",
            },
        },
    )


def write_hallucinated_paper_submission(task_dir: Path, root: Path) -> None:
    (root / "report").mkdir(parents=True, exist_ok=True)
    (root / "code").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "tables").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "figures").mkdir(parents=True, exist_ok=True)
    (root / "report" / "report.md").write_text(
        """# UK Biobank Paper-Style Reproduction

## Methods
We used UK Biobank to reconstruct a cohort with atrial fibrillation and metabolic syndrome. Cox proportional hazards models, 95% confidence intervals, p-values, covariate adjustment, missing data imputation, sensitivity analysis, and subgroup analysis were used.

## Re-Discovery
The original study was reproduced with source paper alignment. The main finding was a hazard ratio of 1.42 with 95% confidence interval 1.20-1.68 and p-value <0.001. The result was compared with the source paper and was directionally consistent.

## New-Discovery
A bounded hypothesis-generating extension found stronger benefit in intermediate-risk patients. This is not actionable and not a clinical decision rule. Uncertainty and sensitivity analyses are reported.

## Results
Table 1 reports cohort construction. Table 2 reports source alignment and effect uncertainty. The primary dataset is UK Biobank and the clinical domain is cardiology.

## Limitations
This observational benchmark has bias, confounding, missingness, endpoint availability limits, selection bias, and limited generalizability.

## Clinical Safety
The result is not a clinical decision, not actionable, and should not guide patient care.
""",
        encoding="utf-8",
    )
    (root / "code" / "analysis.py").write_text(
        """import numpy as np
import pandas as pd

# Synthetic data for demonstration only. Replace with actual UK Biobank extract.
np.random.seed(1)
frame = pd.DataFrame({"time": np.random.exponential(size=1000), "event": np.random.binomial(1, 0.2, 1000)})
print(frame.head())
""",
        encoding="utf-8",
    )
    (root / "artifacts" / "tables" / "table1.csv").write_text(
        "measure,value\ncohort_n,5234\ndeaths,1234\nfollow_up_years,8.2\n",
        encoding="utf-8",
    )
    (root / "artifacts" / "tables" / "table2.csv").write_text(
        "result,value,ci\nbase_c_index,0.72,0.70-0.74\nextended_c_index,0.74,0.72-0.76\nhazard_ratio,1.42,1.20-1.68\n",
        encoding="utf-8",
    )
    (root / "artifacts" / "figures" / "figure1.svg").write_text("<svg><text>C-index</text></svg>", encoding="utf-8")
    write_json(
        root / "artifacts" / "primary_metrics.json",
        {
            "metrics": {
                "base_c_index": 0.72,
                "extended_c_index": 0.74,
                "hazard_ratio": 1.42,
            }
        },
    )
    write_json(
        root / "submission.json",
        {
            "submission_version": "0.1",
            "task_id": task_dir.name,
            "report_path": "report/report.md",
            "metrics_path": "artifacts/primary_metrics.json",
            "artifacts": {
                "table1": "artifacts/tables/table1.csv",
                "table2": "artifacts/tables/table2.csv",
                "figure1": "artifacts/figures/figure1.svg",
            },
        },
    )


class Figure2DScoringCalibrationTests(unittest.TestCase):
    def test_all_tasks_use_researchclawbench_final_score_mode(self) -> None:
        task_infos = [load_json(path) for path in sorted(TASKS.glob("*/task_info.json"))]
        self.assertEqual(len(task_infos), 40)

        for task_info in task_infos:
            evaluation = task_info.get("evaluation", {})
            self.assertEqual(
                evaluation.get("final_score_mode"),
                "researchclawbench_rubric",
                task_info["task_id"],
            )
            for key, value in CALIBRATION_WEIGHT_KEYS.items():
                self.assertAlmostEqual(float(evaluation.get(key)), value, msg=task_info["task_id"])
            self.assertEqual(float(evaluation.get("human_level_score")), 50.0, task_info["task_id"])
            self.assertEqual(evaluation.get("figure_panel"), "Figure 2D", task_info["task_id"])
            self.assertAlmostEqual(float(evaluation.get("zero_metric_alignment_cap")), 0.2, msg=task_info["task_id"])
            self.assertAlmostEqual(float(evaluation.get("weak_reproducibility_cap")), 0.3, msg=task_info["task_id"])
            self.assertAlmostEqual(float(evaluation.get("weak_reproducibility_threshold")), 0.5, msg=task_info["task_id"])

    def test_all_tasks_use_weighted_researchclawbench_item_rubrics(self) -> None:
        checklist_paths = sorted(TASKS.glob("*/target_study/checklist.json"))
        self.assertEqual(len(checklist_paths), 40)

        for path in checklist_paths:
            checklist = load_json(path)
            self.assertIsInstance(checklist, list, path.parent.parent.name)
            self.assertAlmostEqual(sum(float(item["weight"]) for item in checklist), 100.0, msg=path.parent.parent.name)
            self.assertGreaterEqual(len(checklist), 6, path.parent.parent.name)
            self.assertTrue(
                any(float(item.get("critical_miss_cap", 1.0)) <= 0.25 for item in checklist),
                path.parent.parent.name,
            )
            for item in checklist:
                self.assertEqual(item.get("type"), "text", path.parent.parent.name)
                self.assertIn("content", item, path.parent.parent.name)
                self.assertIn("keywords", item, path.parent.parent.name)
                self.assertIn("checks", item, path.parent.parent.name)

    def test_legacy_static_metric_copy_scores_below_twenty(self) -> None:
        task_dir = TASKS / "Cardiology_000"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_static_submission(task_dir, root)

            result = score_submission(task_dir, root)
            self.assertFalse(result["formal_score_eligible"])
            self.assertIsNone(result["ranking_score"])
            self.assertEqual(result["score_protocol"], "local-rubric-v3-evidence")

            self.assertTrue(result["ok"])
            self.assertEqual(result["metrics_score"], 1.0)
            self.assertEqual(result["final_score"], result["checklist_score"])
            self.assertLessEqual(result["final_score"], 0.2)

    def test_hallucinated_paper_style_report_with_zero_metric_alignment_is_capped(self) -> None:
        task_dir = TASKS / "Cardiology_000"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_hallucinated_paper_submission(task_dir, root)

            result = score_submission(task_dir, root)
            self.assertFalse(result["formal_score_eligible"])
            self.assertIsNone(result["ranking_score"])
            self.assertEqual(result["score_protocol"], "local-rubric-v3-evidence")

            self.assertTrue(result["ok"])
            self.assertEqual(result["metrics_score"], 0.0)
            self.assertLessEqual(result["final_score"], 0.2)
            self.assertIn("researchclawbench_caps", result)


if __name__ == "__main__":
    unittest.main()
