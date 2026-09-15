import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"

FIGURE_2D_DOMAINS = {
    "Oncology": "Oncology",
    "Cardiology": "Cardiology",
    "Neurology": "Neurology",
    "InfectiousDisease": "Infectious Disease",
    "Endocrinology": "Endocrinology",
    "Immunology": "Immunology",
    "Respiratory": "Respiratory",
    "Gastroenterology": "Gastroenterology",
    "Hematology": "Hematology",
    "Dermatology": "Dermatology",
}

FIGURE_2D_DOMAIN_ORDER = {
    "Oncology": 1,
    "Cardiology": 2,
    "Neurology": 3,
    "InfectiousDisease": 4,
    "Endocrinology": 5,
    "Immunology": 6,
    "Respiratory": 7,
    "Gastroenterology": 8,
    "Hematology": 9,
    "Dermatology": 10,
}

BANNED_DOMAIN_CODES = {
    "HealthServicesPharmacoepi",
    "ObstetricsPediatrics",
    "GastroHepRenal",
    "HematologyImmunology",
    "EndocrineMetabolic",
    "RespiratoryCriticalCare",
    "NeurologyPsychiatry",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Figure2DDomainAlignmentTests(unittest.TestCase):
    def test_task_infos_use_exact_figure_2d_domains(self) -> None:
        task_infos = [load_json(path) for path in sorted(TASKS.glob("*/task_info.json"))]
        self.assertEqual(len(task_infos), 40)

        counts = Counter(info["domain_code"] for info in task_infos)
        self.assertEqual(set(counts), set(FIGURE_2D_DOMAINS))
        self.assertEqual(counts, Counter({domain_code: 4 for domain_code in FIGURE_2D_DOMAINS}))

        for info in task_infos:
            domain_code = info["domain_code"]
            self.assertNotIn(domain_code, BANNED_DOMAIN_CODES)
            self.assertEqual(info["domain"], FIGURE_2D_DOMAINS[domain_code])
            self.assertEqual(info["domain_index"], FIGURE_2D_DOMAIN_ORDER[domain_code])
            self.assertTrue(
                info["task_id"].startswith(f"{domain_code}_"),
                f"{info['task_id']} should use domain prefix {domain_code}_",
            )

    def test_index_and_literature_map_match_figure_2d_domains(self) -> None:
        index = load_json(TASKS / "clinicalrepbench_index.json")
        literature_map = load_json(TASKS / "clinicalrepbench_literature_map.json")

        for payload in (index, literature_map):
            tasks = payload["tasks"]
            self.assertEqual(len(tasks), 40)
            counts = Counter(item["task_id"].rsplit("_", 1)[0] for item in tasks)
            self.assertEqual(counts, Counter({domain_code: 4 for domain_code in FIGURE_2D_DOMAINS}))
            for item in tasks:
                prefix = item["task_id"].rsplit("_", 1)[0]
                self.assertIn(prefix, FIGURE_2D_DOMAINS)
                self.assertNotIn(prefix, BANNED_DOMAIN_CODES)
                if "domain" in item:
                    self.assertEqual(item["domain"], FIGURE_2D_DOMAINS[prefix])


if __name__ == "__main__":
    unittest.main()
