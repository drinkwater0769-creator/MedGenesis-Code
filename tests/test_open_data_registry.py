import unittest
from unittest.mock import patch
import tempfile
from collections import Counter
from pathlib import Path

from clinicalclawbench.open_data.prepare import plan_open_data_task, prepare_open_data_task
from clinicalclawbench.open_data.registry import discover_open_tasks, load_source_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"


class OpenDataRegistryTest(unittest.TestCase):
    def test_all_open_data_tasks_have_runnable_manifests(self) -> None:
        tasks = discover_open_tasks(TASKS_DIR)

        self.assertEqual(len(tasks), 15)
        self.assertEqual(
            Counter(task.dataset for task in tasks),
            {"NHANES": 10, "TCGA/GDC": 4, "FAERS": 1},
        )

        for task in tasks:
            manifest = load_source_manifest(task.task_dir)
            data_manifest = task.data_manifest

            self.assertEqual(manifest["task_id"], task.task_id)
            self.assertEqual(manifest["dataset"], task.dataset)
            self.assertIn(manifest["provider"], {"nhanes", "tcga_gdc", "faers_openfda"})
            self.assertIn("extract", manifest)
            self.assertNotIn("extractor script pending", data_manifest.get("build_status", ""))

    def test_download_plan_is_available_for_each_open_provider(self) -> None:
        for task in discover_open_tasks(TASKS_DIR):
            with self.subTest(task=task.task_id):
                plan = plan_open_data_task(task.task_dir)
                self.assertEqual(plan["dataset"], task.dataset)
                self.assertGreater(len(plan["downloads"]), 0)

    def test_neurology_preparation_uses_paper_specific_builder(self) -> None:
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp, patch(
            "clinicalclawbench.public_nhanes_neuro_002.build_extract",
            return_value=(pd.DataFrame({"seqn": [1, 2]}), {"n_analytic": 2}),
        ) as builder:
            workspace = Path(tmp) / "workspace"
            cache = Path(tmp) / "cache"
            cache.mkdir()
            manifest = load_source_manifest(TASKS_DIR / "Neurology_002")
            for component in manifest["components"]:
                (cache / component["file"]).write_text("fixture")
            result = prepare_open_data_task(
                TASKS_DIR / "Neurology_002", workspace, cache_dir=cache, download=False,
            )
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["task_id"], "Neurology_002")
            self.assertEqual(builder.call_args.args[:3], (cache, cache / "nhanes3", cache / "lmf"))
            self.assertEqual(builder.call_args.args[3], workspace / "data/analytic_extract.csv")
            self.assertTrue((cache / "nhanes3/NHANES_III_MORT_2019_PUBLIC.dat").is_file())

    def test_neurology_without_download_requires_staged_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "clinicalclawbench.public_nhanes_neuro_002.build_extract",
        ) as builder:
            with self.assertRaisesRegex(FileNotFoundError, "Missing Neurology_002 source file"):
                prepare_open_data_task(TASKS_DIR / "Neurology_002", Path(tmp), download=False)
            builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
