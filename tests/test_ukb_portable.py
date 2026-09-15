import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from clinicalrepbench.ukb_io import canonical_column, inspect_inputs, prepare_inputs, verify_prepared
from clinicalrepbench.ukb_diagnostic import paired_death, endpoint_masks, parse_dates, run_neurology_diagnostic

TASK = Path(__file__).resolve().parents[1] / "tasks/Neurology_000"
PROFILE = "neurology000-crude-v1"


def fixture(path: Path, *, rap=False):
    # Entirely synthetic software-test fixture, never a benchmark performance result.
    data = {
        "eid": [str(i) for i in range(1, 31)], "31-0.0": [i % 2 for i in range(30)],
        "53-0.0": ["2010-01-01"] * 30, "21022-0.0": [55] * 30,
        "46-0.0": [30] * 30, "47-0.0": [32] * 30, "20002-0.0": [0] * 30,
        "41270-0.0": ["F03"] * 10 + [""] * 20,
        "41280-0.0": ["2016-01-01"] * 10 + [""] * 20,
        "40000-0.0": ["2018-01-01"] * 10 + [""] * 20,
        "40001-0.0": ["F03"] * 10 + [""] * 20,
        "40002-0.0": [""] * 30,
    }
    frame = pd.DataFrame(data)
    if rap:
        frame.columns = ["eid" if c == "eid" else "p" + c.replace("-", "_i").replace(".", "_a") for c in frame]
    frame.to_csv(path, index=False)
    return frame


class UKBPortableTests(unittest.TestCase):
    def test_canonical_names(self):
        for name in ["53-0.0", "f.53.0.0", "53.0.0", "p53_i0", "participant.p53_i0_a0"]:
            self.assertEqual(canonical_column(name), "53-0.0")
        self.assertEqual(canonical_column("participant.eid"), "eid")

    def test_unadvertised_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not advertised"):
            inspect_inputs(TASK, [], "ukb-candidate-input-v1")

    def test_headers_and_pairs(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "source.csv"
            f = fixture(p, rap=True)
            self.assertTrue(inspect_inputs(TASK, [p], PROFILE)["input_headers_ok"])
            f = f.rename(columns={"p41280_i0_a0": "p41280_i0_a1"})
            f.to_csv(p, index=False)
            result = inspect_inputs(TASK, [p], PROFILE)
            self.assertFalse(result["input_headers_ok"])
            self.assertTrue(result["pairing_errors"])

    def test_prepare_hashes_and_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); p = root / "source.csv"; fixture(p)
            output = root / "prepared"
            prepare_inputs(TASK, [p], output, PROFILE, "synthetic-test", "not_verified", 7)
            self.assertTrue(verify_prepared(output, TASK)["ok"])
            with (output / "source_1.parquet").open("ab") as handle:
                handle.write(b"tampered")
            self.assertFalse(verify_prepared(output, TASK)["ok"])

    def test_provenance_profile_and_task_are_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); p = root / "source.csv"; fixture(p)
            output = root / "prepared"
            prepare_inputs(TASK, [p], output, PROFILE, "synthetic-test", "not_verified", 7)
            manifest = output / "provenance.json"
            data = json.loads(manifest.read_text())
            data["task_id"] = "Cardiology_000"
            data["profile"] = "unknown"
            manifest.write_text(json.dumps(data))
            result = verify_prepared(output, TASK)
            self.assertFalse(result["ok"])
            self.assertIn("task_id mismatch", result["errors"])
            self.assertIn("unsupported execution profile", result["errors"])

    def test_duplicate_keys_fail_without_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); p = root / "source.csv"; f = fixture(p)
            f.loc[29, "eid"] = "1"; f.to_csv(p, index=False)
            with self.assertRaisesRegex(ValueError, "duplicate participant"):
                prepare_inputs(TASK, [p], root / "prepared", PROFILE, "test", "not_verified", 7)
            self.assertFalse((root / "prepared").exists())

    def test_mismatched_join_keys_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); p = root / "original.csv"; f = fixture(p)
            f[["eid", "31-0.0"]].iloc[:-1].to_csv(root / "one.csv", index=False)
            f.drop(columns=["31-0.0"]).to_csv(root / "two.csv", index=False)
            with self.assertRaisesRegex(ValueError, "key sets differ"):
                prepare_inputs(TASK, [root / "one.csv", root / "two.csv"], root / "prepared", PROFILE, "test", "not_verified")

    def test_public_repository_output_is_refused(self):
        with self.assertRaisesRegex(ValueError, "outside the public repository"):
            prepare_inputs(TASK, [], TASK / "do-not-write", PROFILE, "test", "not_verified")

    def test_death_causes_stay_with_their_registry_instance(self):
        frame = pd.DataFrame({"40000-0.0": ["2015-01-01", "2015-01-01"],
                              "40000-1.0": ["2018-01-01", "2015-01-01"],
                              "40001-0.0": ["I21", "I21"], "40001-1.0": ["F03", "F03"],
                              "40002-0.0": ["", ""]})
        death, primary, mention = paired_death(frame)
        self.assertEqual(primary.tolist(), [False, True])
        self.assertEqual(mention.tolist(), [False, True])
        self.assertTrue(death.eq(pd.Timestamp("2015-01-01")).all())

    def test_landmark_and_post_death_events(self):
        baseline = pd.to_datetime(pd.Series(["2010-01-01"] * 3))
        death = pd.to_datetime(pd.Series(["2012-01-01", "2014-01-01", None]))
        hospital = pd.to_datetime(pd.Series([None, "2016-01-01", "2016-01-01"]))
        eligible, incident, *_ = endpoint_masks(baseline, death, hospital)
        self.assertEqual(eligible.tolist(), [False, True, True])
        self.assertEqual(incident.tolist(), [False, False, True])

    def test_special_dates_are_not_real_events(self):
        out = parse_dates(pd.Series(["1909-09-09", "2037-07-07", "2018-01-01"]))
        self.assertEqual(out.isna().tolist(), [True, True, False])

    def test_complete_diagnostic_is_chunk_invariant_and_not_rankable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); p = root / "source.csv"; fixture(p)
            prepared = root / "prepared"
            prepare_inputs(TASK, [p], prepared, PROFILE, "synthetic-test", "not_verified", 7)
            run_neurology_diagnostic(prepared, TASK, root / "one.json", 7)
            run_neurology_diagnostic(prepared, TASK, root / "two.json", 13)
            self.assertEqual((root / "one.json").read_bytes(), (root / "two.json").read_bytes())
            result = json.loads((root / "one.json").read_text())
            self.assertEqual(result["metrics"]["cohort_n"], 30)
            self.assertEqual(result["metrics"]["n_incident_dementia"], 10)
            self.assertFalse(result["formal_score_eligible"])
            self.assertFalse(result["full_paper_reproduction"])
            self.assertNotIn('"eid"', (root / "one.json").read_text())


if __name__ == "__main__":
    unittest.main()
