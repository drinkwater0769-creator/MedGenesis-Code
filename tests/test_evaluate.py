import unittest

from clinicalclawbench.evaluate import score_metric, score_metrics


class EvaluateTest(unittest.TestCase):
    def test_score_metric_within_tolerance(self) -> None:
        self.assertEqual(score_metric(5.44, 5.45, 0.02), 1.0)

    def test_score_metrics_missing_metric(self) -> None:
        target = {
            "metrics": [
                {"id": "cohort_n", "value": 20, "tolerance_abs": 0, "weight": 1.0},
                {"id": "or_main", "value": 5.44, "tolerance_abs": 0.01, "weight": 2.0}
            ]
        }
        submission = {"metrics": {"cohort_n": 20}}
        result = score_metrics(target, submission)
        self.assertAlmostEqual(result["objective_score"], 1.0 / 3.0, places=6)


if __name__ == "__main__":
    unittest.main()
