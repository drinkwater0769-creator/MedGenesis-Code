import json
import tempfile
import unittest
from pathlib import Path

from clinicalrepbench.evaluate import score_submission


TASK_DIR = Path(__file__).resolve().parents[1] / "tasks" / "Dermatology_000"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def exact_target_metrics() -> dict:
    target = json.loads((TASK_DIR / "target_study" / "target_metrics.json").read_text(encoding="utf-8"))
    return {metric["id"]: metric["value"] for metric in target["metrics"]}


def write_submission(
    root: Path,
    *,
    report_text: str,
    code_text: str = "",
    table2_text: str = "term,n\nPruritus,10\nRash,8\nConjunctivitis,5\n",
) -> None:
    (root / "report").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "tables").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "figures").mkdir(parents=True, exist_ok=True)
    (root / "report" / "report.md").write_text(report_text, encoding="utf-8")
    (root / "artifacts" / "tables" / "table1.csv").write_text("measure,value\ncohort_n,100\n", encoding="utf-8")
    (root / "artifacts" / "tables" / "table2.csv").write_text(table2_text, encoding="utf-8")
    (root / "artifacts" / "figures" / "figure1.svg").write_text("<svg><text>Dupilumab FAERS</text></svg>", encoding="utf-8")
    write_json(root / "artifacts" / "primary_metrics.json", {"metrics": exact_target_metrics()})
    if code_text:
        (root / "code").mkdir(parents=True, exist_ok=True)
        (root / "code" / "analysis.py").write_text(code_text, encoding="utf-8")
    write_json(
        root / "submission.json",
        {
            "submission_version": "0.1",
            "task_id": "Dermatology_000",
            "report_path": "report/report.md",
            "metrics_path": "artifacts/primary_metrics.json",
            "artifacts": {
                "table1": "artifacts/tables/table1.csv",
                "table2": "artifacts/tables/table2.csv",
                "figure1": "artifacts/figures/figure1.svg",
            },
        },
    )


class Dermatology000HardModeTests(unittest.TestCase):
    def test_uses_researchclawbench_rubric_as_final_score(self) -> None:
        checklist = json.loads((TASK_DIR / "target_study" / "checklist.json").read_text(encoding="utf-8"))
        task_info = json.loads((TASK_DIR / "task_info.json").read_text(encoding="utf-8"))

        self.assertIsInstance(checklist, list)
        self.assertEqual(task_info["evaluation"]["final_score_mode"], "researchclawbench_rubric")
        self.assertAlmostEqual(sum(float(item["weight"]) for item in checklist), 100.0)
        for item in checklist:
            self.assertEqual(item.get("type"), "text")
            self.assertIn("content", item)
            self.assertIn("checks", item)

    def test_static_metric_copy_cannot_score_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_submission(
                root,
                report_text="""# Static Dermatology Submission

## Methods
Static report.

## Re-Discovery
Static report.

## New-Discovery
Static report.

## Results
Static report.

## Limitations
Static report.

## Clinical Safety
Static report.
""",
            )

            result = score_submission(TASK_DIR, root)

            self.assertTrue(result["ok"])
            self.assertEqual(result["metrics_score"], 1.0)
            self.assertEqual(result["gate_score"], 1.0)
            self.assertEqual(result["final_score"], result["checklist_score"])
            self.assertLessEqual(result["final_score"], 0.2)

    def test_generic_open_data_reference_stays_low(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_submission(
                root,
                report_text="""# Open-Data Reference Report

## Methods
This reference run prepared the official open dataset declared for Dermatology_000 and generated the task analytic extract using the bundled source manifest.

## Re-Discovery
The run records the cohort size and core extract completeness needed to reproduce the source-study workflow.

## New-Discovery
The generated extract can be extended with task-specific subgroup or sensitivity analyses once target article-specific estimands are adjudicated.

## Limitations
This generic reference records data availability and extract integrity.

## Clinical Safety
The output is a benchmark artifact, not a clinical decision tool, and should not be interpreted as causal or actionable patient-level evidence.
""",
                table2_text="column,missing_n\nsafetyreportid,0\nreceivedate,0\nserious,0\nprimary_drug,0\n",
            )

            result = score_submission(TASK_DIR, root)

            self.assertTrue(result["ok"])
            self.assertLessEqual(result["final_score"], 0.25)

    def test_paper_like_submission_without_source_data_is_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_submission(
                root,
                report_text="""# Dupilumab FAERS Reproduction

## Methods
We reconstructed a FAERS disproportionality analysis for dupilumab from Q2 2017 to Q4 2023. The analytic frame uses the four-fold case/non-case table for drug-event pairs, deduplicates safety reports, and computes Reporting Odds Ratio, Proportional Reporting Ratio, Bayesian Confidence Propagation Neural Network information component, and Empirical Bayesian Geometric Mean.

## Re-Discovery
The source study reported 11,547,571 total AE reports, 5,335 suspected dupilumab reports, 307 Preferred Terms, and 27 System Organ Classes. Female reports exceeded male reports, 56.08% vs 34.65%. The 45-65 year group had the largest share at 21.34%, the US contributed 98.07%, and 2023 contributed 34.25% compared with 0.42% in 2017. Common AEs included pruritus, product use in unapproved indication, and rash. High signal-strength findings included rebound atopic dermatitis, rebound eczema, dermatitis atopic, and dry skin.

## New-Discovery
Potential newer signals included dry eye, eye pruritus, ocular hyperaemia, eye irritation, conjunctivitis, vision blurred, sleep disorder, injection site dryness, and injection site eczema. These are hypothesis-generating and need clinical adjudication.

## Results
Table 1 summarizes report flow. Table 2 ranks Preferred Terms with ROR, PRR, IC025, and EBGM05 fields. Figure 1 shows the strongest dermatologic and ocular signals.

## Limitations
FAERS is a spontaneous reporting system with duplicate reports, underreporting, missing denominators, stimulated reporting, confounding by indication, and co-medication bias. Disproportionality is not incidence and does not establish causality.

## Clinical Safety
The analysis supports dermatology pharmacovigilance review only. It should not be used as patient-level evidence to stop or start dupilumab.
""",
                code_text="""
drug = "dupilumab"
quarter_start = "2017Q2"
quarter_end = "2023Q4"
total_reports = 11547571
dupilumab_reports = 5335
preferred_terms = 307
system_organ_classes = 27
def ror(a, b, c, d): return (a / b) / (c / d)
def prr(a, b, c, d): return (a / (a + b)) / (c / (c + d))
def bcpnn_information_component(a, b, c, d): return "IC025"
def ebgm(a, b, c, d): return "EBGM05"
non_case = "all other FAERS drug-event reports"
""",
                table2_text="preferred_term,ror,prr,ic025,ebgm05\nrebound atopic dermatitis,12,9,3,5\nrebound eczema,11,8,3,5\ndry eye,6,4,2,3\nconjunctivitis,5,4,2,3\n",
            )

            result = score_submission(TASK_DIR, root)

            self.assertTrue(result["ok"])
            # Paper-like prose and copied target values are not executed research.
            self.assertLessEqual(result["final_score"], 0.2)
            self.assertIn("missing_source_data_use_cap", {
                cap["id"] for cap in result["researchclawbench_caps"]
            })

    def test_generic_faers_signal_report_stays_below_twenty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_submission(
                root,
                report_text="""# Dupilumab FAERS Signal Report

## Methods
We reconstructed the pharmacovigilance workflow for dupilumab using FAERS via the openFDA API. The analytic cohort included reports where dupilumab was listed as primary suspect or concomitant drug. Disproportionality analysis calculated the Reporting Odds Ratio and Proportional Reporting Ratio for MedDRA Preferred Terms. A signal was defined as at least 3 reports and the lower bound of the 95% confidence interval for ROR greater than 1. Since exact source-study dates are redacted, we assumed a data extraction window from dupilumab approval in 2017 to the present.

## Re-Discovery
The analysis identified known adverse events, most notably ocular surface disorders such as conjunctivitis and keratitis, and injection site reactions. The ROR for conjunctivitis was elevated, consistent with clinical trial data and post-marketing surveillance.

## New-Discovery
We analyzed head and neck dermatitis and facial erythema. These terms showed elevated RORs, but FAERS only indicates reporting association, not causality. The signal may be confounded by underlying atopic dermatitis.

## Results
Dupilumab was associated with thousands of reports. Conjunctivitis showed an assumed ROR of 4.5 with 95% CI 4.2-4.8. Injection site erythema had an assumed ROR of 3.2. Facial erythema had an assumed ROR of 2.8.

## Limitations
FAERS is a spontaneous reporting system with underreporting, variable report quality, duplicate reports, missing denominators, confounding by indication, and incomplete medication data. These data cannot establish causality.

## Clinical Safety
Clinicians should monitor ocular adverse events and injection site reactions, but these reporting signals should not be treated as causal adverse-event estimates.
""",
                code_text="""
import numpy as np

def calculate_disproportionality(a, b, c, d):
    ror = (a * d) / (b * c)
    se_ln_ror = np.sqrt(1/a + 1/b + 1/c + 1/d)
    ror_ci_lower = np.exp(np.log(ror) - 1.96 * se_ln_ror)
    prr = (a / (a + b)) / (c / (c + d))
    return {"ROR": ror, "ROR_95CI_Lower": ror_ci_lower, "PRR": prr}
""",
                table2_text="Adverse Event (PT),Report Count,ROR,95% CI Lower,95% CI Upper,PRR\nConjunctivitis,3800,4.50,4.20,4.80,4.35\nInjection site erythema,2100,3.20,2.90,3.50,3.15\nFacial erythema,850,2.80,2.40,3.30,2.75\nKeratitis,420,3.80,3.10,4.60,3.70\n",
            )

            result = score_submission(TASK_DIR, root)

            self.assertTrue(result["ok"])
            self.assertLessEqual(result["final_score"], 0.2)


if __name__ == "__main__":
    unittest.main()
