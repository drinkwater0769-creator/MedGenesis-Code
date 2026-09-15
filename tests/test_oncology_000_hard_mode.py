import json
import tempfile
import unittest
from pathlib import Path

from clinicalclawbench.evaluate import score_submission


TASK_DIR = Path(__file__).resolve().parents[1] / "tasks" / "Oncology_000"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def exact_target_metrics() -> dict:
    target = json.loads((TASK_DIR / "target_study" / "target_metrics.json").read_text(encoding="utf-8"))
    return {metric["id"]: metric["value"] for metric in target["metrics"]}


def write_static_submission(root: Path, include_bad_analysis_code: bool = False) -> None:
    (root / "report").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "tables").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "figures").mkdir(parents=True, exist_ok=True)
    (root / "report" / "report.md").write_text(
        "\n".join(
            [
                "# Static Oncology_000 Submission",
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
    (root / "artifacts" / "tables" / "table2.csv").write_text("gene,pct\nTP53,50\n", encoding="utf-8")
    (root / "artifacts" / "figures" / "figure1.svg").write_text("<svg/>", encoding="utf-8")
    write_json(root / "artifacts" / "primary_metrics.json", {"metrics": exact_target_metrics()})
    if include_bad_analysis_code:
        (root / "code").mkdir(parents=True, exist_ok=True)
        (root / "code" / "analysis.py").write_text(
            "\n".join(
                [
                    "import json",
                    "import pandas as pd",
                    "frame = pd.read_csv('data/analytic_extract.csv')",
                    "metrics = {'sequenced_patient_n': len(frame)}",
                    "open('artifacts/primary_metrics.json', 'w').write(json.dumps({'metrics': metrics}))",
                ]
            ),
            encoding="utf-8",
        )
    write_json(
        root / "submission.json",
        {
            "submission_version": "0.1",
            "task_id": "Oncology_000",
            "report_path": "report/report.md",
            "metrics_path": "artifacts/primary_metrics.json",
            "artifacts": {
                "table1": "artifacts/tables/table1.csv",
                "table2": "artifacts/tables/table2.csv",
                "figure1": "artifacts/figures/figure1.svg",
            },
        },
    )


def write_rawls_style_analysis_code(root: Path) -> None:
    (root / "report" / "report.md").write_text(
        """# Oncology_000 TCGA-LUAD Molecular Profile Reproduction

## Methods
The analysis rebuilt the cohort from `data/source/tcga-luad_cases.json`, the sequencing denominator from GDC MAF index case submitter IDs plus observed MAF tumor barcodes, and the driver matrix from raw `.maf`/`.maf.gz` files under `data/source/tcga-luad_maf/`. Patient IDs were normalized to the first 12 characters of `Tumor_Sample_Barcode`. Non-silent mutations excluded Silent, Intron, IGR, 3'UTR, 5'UTR, 3'Flank, 5'Flank, and RNA classifications. Percentages are on a 0-100 scale.

## Re-Discovery
The sequenced denominator was 559 patients. Non-silent driver alteration frequencies were TP53 50.6261%, KRAS 26.6547%, EGFR 13.4168%, STK11 11.8068%, and KEAP1 17.5313%. These results reproduce the expected dominant LUAD driver pattern using only the open masked mutation files.

## New-Discovery
EGFR and KRAS were evaluated as a compact benchmark sanity check because concurrent activating events are expected to be uncommon. Among patients with either EGFR or KRAS non-silent mutation, 99.5516% were exclusive and 1 patients carried both markers. This supports the utility of a simple exclusivity check as a reproducibility flag, not as a clinical decision rule.

## Results
The clinical file contained 585 LUAD cases. The MAF-derived sequenced denominator contained 559 patients and 135940 deduplicated non-silent mutation records. Death events were present in 36.0153% of cases with known vital status. Table 1 summarizes cohort construction and endpoint availability; Table 2 lists driver-gene frequencies; Figure 1 visualizes the primary driver frequencies.

## Limitations
The analysis uses open GDC masked somatic mutation calls and therefore cannot fully reconstruct all molecular modalities, copy-number events, fusions, treatment exposures, or full survival models from the source publication. Clinical endpoint fields are incomplete and observational. Multiple aliquots and variant records were deduplicated conservatively by patient, gene, locus, alleles, and classification. Statistical significance was not interpreted as clinical significance.

## Clinical Safety
These outputs are for benchmark reproduction and quality control only. They should not guide patient care, molecular tumor board decisions, prognostication, trial eligibility, or therapy selection without clinically validated assays, complete pathology review, contemporary annotation, and appropriate clinical governance.
""",
        encoding="utf-8",
    )
    (root / "code").mkdir(parents=True, exist_ok=True)
    (root / "code" / "analysis.py").write_text(
        r'''
from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source"
MAF_DIR = SOURCE / "tcga-luad_maf"
DRIVER_GENES = ["TP53", "KRAS", "EGFR", "STK11", "KEAP1"]
EXCLUDED = {"Silent", "Intron", "IGR", "3'UTR", "5'UTR", "3'Flank", "5'Flank", "RNA"}


def load_hits(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return list(payload.get("data", {}).get("hits", []))


def patient_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:12].upper() if text else None


def pct(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator) * 100.0, 4) if denominator else 0.0


def open_maf(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", newline="", errors="replace")
    return path.open("rt", newline="", errors="replace")


def load_cases() -> tuple[dict[str, dict], list[dict]]:
    cases = {}
    rows = []
    for hit in load_hits(SOURCE / "tcga-luad_cases.json"):
        pid = patient_id(hit.get("submitter_id") or hit.get("case_id"))
        if not pid:
            continue
        row = {
            "patient_id": pid,
            "vital_status": (hit.get("demographic") or {}).get("vital_status"),
        }
        cases[pid] = row
        rows.append(row)
    return cases, rows


def index_patients() -> set[str]:
    patients = set()
    for hit in load_hits(SOURCE / "tcga-luad_masked_maf_files.json"):
        for case in hit.get("cases") or []:
            pid = patient_id(case.get("submitter_id") or case.get("case_id"))
            if pid:
                patients.add(pid)
    return patients


def load_mutations():
    observed = set()
    non_silent_variants = set()
    driver_patients = defaultdict(set)
    for path in sorted([p for p in MAF_DIR.iterdir() if p.is_file() and p.name.endswith((".maf", ".maf.gz"))]):
        with open_maf(path) as handle:
            reader = csv.DictReader((line for line in handle if not line.startswith("#")), delimiter="\t")
            for row in reader:
                pid = patient_id(row.get("Tumor_Sample_Barcode"))
                if not pid:
                    continue
                observed.add(pid)
                classification = (row.get("Variant_Classification") or "").strip()
                if classification in EXCLUDED:
                    continue
                key = (
                    pid,
                    (row.get("Hugo_Symbol") or "").upper().strip(),
                    row.get("Chromosome") or "",
                    row.get("Start_Position") or "",
                    row.get("End_Position") or "",
                    row.get("Reference_Allele") or "",
                    row.get("Tumor_Seq_Allele2") or row.get("Tumor_Seq_Allele1") or "",
                    classification,
                )
                if key in non_silent_variants:
                    continue
                non_silent_variants.add(key)
                gene = key[1]
                if gene in DRIVER_GENES:
                    driver_patients[gene].add(pid)
    return observed, non_silent_variants, driver_patients


def main() -> None:
    (ROOT / "artifacts").mkdir(exist_ok=True)
    cases, clinical_rows = load_cases()
    observed, non_silent_variants, driver_patients = load_mutations()
    sequenced = index_patients() | observed
    sequenced_n = len(sequenced)

    egfr = driver_patients["EGFR"] & sequenced
    kras = driver_patients["KRAS"] & sequenced
    altered = egfr | kras
    overlap = len(egfr & kras)
    exclusive = len(altered) - overlap
    vital_known = [row for row in clinical_rows if str(row.get("vital_status") or "").strip()]
    deaths = [row for row in vital_known if str(row.get("vital_status")).strip().lower() == "dead"]
    metrics = {
        "luad_case_n": len(cases),
        "sequenced_patient_n": sequenced_n,
        "non_silent_mutation_n": len(non_silent_variants),
        "tp53_mutated_pct": pct(len(driver_patients["TP53"] & sequenced), sequenced_n),
        "kras_mutated_pct": pct(len(kras), sequenced_n),
        "egfr_mutated_pct": pct(len(egfr), sequenced_n),
        "stk11_mutated_pct": pct(len(driver_patients["STK11"] & sequenced), sequenced_n),
        "keap1_mutated_pct": pct(len(driver_patients["KEAP1"] & sequenced), sequenced_n),
        "egfr_kras_overlap_n": overlap,
        "egfr_kras_exclusive_n": exclusive,
        "egfr_kras_exclusive_pct_among_altered": pct(exclusive, len(altered)),
        "death_event_pct": pct(len(deaths), len(vital_known)),
    }
    (ROOT / "artifacts" / "primary_metrics.json").write_text(
        json.dumps({"metrics": metrics}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
'''.lstrip(),
        encoding="utf-8",
    )
    write_json(
        root / "artifacts" / "primary_metrics.json",
        {
            "metrics": {
                "death_event_pct": 36.0153,
                "egfr_kras_exclusive_n": 222,
                "egfr_kras_exclusive_pct_among_altered": 99.5516,
                "egfr_kras_overlap_n": 1,
                "egfr_mutated_pct": 13.4168,
                "keap1_mutated_pct": 17.5313,
                "kras_mutated_pct": 26.6547,
                "luad_case_n": 585,
                "non_silent_mutation_n": 135940,
                "sequenced_patient_n": 559,
                "stk11_mutated_pct": 11.8068,
                "tp53_mutated_pct": 50.6261,
            }
        },
    )


def write_high_text_weak_repro_submission(root: Path) -> None:
    write_static_submission(root, include_bad_analysis_code=False)
    (root / "artifacts" / "primary_metrics.json").write_text(
        json.dumps({"metrics": exact_target_metrics()}, indent=2),
        encoding="utf-8",
    )
    (root / "report" / "report.md").write_text(
        """# TCGA-LUAD GDC Reproduction

## Methods
This submission reproduces PMID 25079552, the Nature 2014 comprehensive molecular profiling of lung adenocarcinoma, using TCGA-LUAD GDC open masked somatic mutation MAF files. The sequenced denominator is defined by clinical subset intersection with sequenced patients from the masked somatic MAF index. The workflow records endpoint availability, death event fields, censoring and follow-up limits, tumor stage and TNM limitations, and driver-gene molecular subtype separation.

## Re-Discovery
The molecular subtype frame uses TP53, KRAS, EGFR, STK11, and KEAP1 driver patterns, with EGFR/KRAS subtype separation and a paper alignment table. The analysis acknowledges open GDC, harmonized masked files, publication freeze differences, copy-number, methylation, RNA, fusion, and multi-platform gaps.

## New-Discovery
EGFR/KRAS exclusivity is a bounded sensitivity analysis with uncertainty boundaries, p-value and confidence interval language reserved for validation. It is not a clinical decision rule and should not guide patient care.

## Results
Kaplan-Meier, Cox, hazard ratio, censoring, follow-up, multivariable tumor stage, and stage-adjusted analyses are delimited because the open masked scaffold cannot fully reproduce the original multi-platform survival model.

## Limitations
The study has observational confounding, bias, missingness, endpoint availability limits, generalizability limits, assumptions, and robustness concerns. Statistical significance is separated from clinical significance.

## Clinical Safety
These benchmark outputs require clinical-grade validated assay workflows and are not suitable for individual treatment.
""",
        encoding="utf-8",
    )
    (root / "artifacts" / "tables" / "table2.csv").write_text(
        "gene,mutated_pct\nTP53,50\nKRAS,27\nEGFR,13\nSTK11,12\nKEAP1,18\nBRAF,7\nMET,4\nERBB2,3\nALK,1\nRBM10,8\nNF1,9\n",
        encoding="utf-8",
    )
    (root / "artifacts" / "tables" / "table3.csv").write_text(
        "analysis,value,note\npaper_alignment,open_gdc_masked_maf,copy-number methylation RNA fusion unavailable\nsurvival,censored,TNM stage-adjusted Cox not fully reproduced\nnew_discovery,EGFR_KRAS_exclusivity,bounded sensitivity\n",
        encoding="utf-8",
    )
    (root / "code").mkdir(parents=True, exist_ok=True)
    (root / "code" / "analysis.py").write_text(
        """import json
from pathlib import Path

# Reproducibility smoke script intentionally weak: it references raw inputs but only computes one metric.
# tcga-luad_cases.json tcga-luad_masked_maf_files.json tcga-luad_maf clinical_subset isin(sequenced .maf.gz gzip
# variant_classification silent intron 3'utr TP53 KRAS EGFR STK11 KEAP1
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/primary_metrics.json').write_text(json.dumps({'metrics': {'non_silent_mutation_n': 198}}))
""",
        encoding="utf-8",
    )


class Oncology000HardModeTest(unittest.TestCase):
    def test_checklist_uses_researchclawbench_schema(self) -> None:
        checklist = json.loads((TASK_DIR / "target_study" / "checklist.json").read_text(encoding="utf-8"))

        self.assertIsInstance(checklist, list)
        self.assertGreater(len(checklist), 0)
        for item in checklist:
            self.assertIn(item.get("type", "text"), {"text", "image"})
            self.assertIn("content", item)
            self.assertIn("keywords", item)
            self.assertIn("weight", item)

    def test_static_submission_without_analysis_code_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_static_submission(root)

            result = score_submission(TASK_DIR, root)

            self.assertFalse(result["ok"])
            self.assertLess(result["final_score"], 1.0)

    def test_precomputed_extract_script_cannot_score_high_on_hidden_raw_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_static_submission(root, include_bad_analysis_code=True)

            result = score_submission(TASK_DIR, root)

            self.assertTrue(result["ok"])
            self.assertEqual(result["metrics_score"], 1.0)
            self.assertGreaterEqual(result["gate_score"], 0.8)
            self.assertLessEqual(result["checklist_score"], 0.2)
            self.assertEqual(result["reproducibility_score"], 0.0)
            self.assertLessEqual(result["final_score"], 0.2)

    def test_rawls_style_script_is_calibrated_near_thirty_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_static_submission(root)
            write_rawls_style_analysis_code(root)

            result = score_submission(TASK_DIR, root)

            self.assertTrue(result["ok"])
            self.assertLessEqual(result["metrics_score"], 0.5)
            self.assertLessEqual(result["checklist_score"], 0.35)
            self.assertGreaterEqual(result["final_score"], 0.2)
            self.assertLessEqual(result["final_score"], 0.3)

    def test_researchclawbench_mode_uses_rubric_as_final_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_static_submission(root)
            write_rawls_style_analysis_code(root)

            result = score_submission(TASK_DIR, root)

            self.assertTrue(result["ok"])
            self.assertNotEqual(result["metrics_score"], result["checklist_score"])
            self.assertEqual(result["final_score"], result["checklist_score"])

    def test_weak_raw_reproducibility_caps_agent_near_thirty_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_high_text_weak_repro_submission(root)

            result = score_submission(TASK_DIR, root)

            self.assertTrue(result["ok"])
            self.assertGreater(result["metrics_score"], 0.9)
            self.assertGreater(result["checklist_score"], 0.3)
            self.assertGreater(result["reproducibility_score"], 0.0)
            self.assertLess(result["reproducibility_score"], 0.5)
            self.assertEqual(result["final_score"], 0.3)
            self.assertIn("weak_reproducibility_cap", {cap["id"] for cap in result["researchclawbench_caps"]})


if __name__ == "__main__":
    unittest.main()
