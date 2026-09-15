from __future__ import annotations

import gzip
import json
import math
import shutil
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from clinicalrepbench.open_data.tcga import download_cases


GDC_FILES_ENDPOINT = "https://api.gdc.cancer.gov/files"
GDC_DATA_ENDPOINT = "https://api.gdc.cancer.gov/data"
DOWNLOAD_TIMEOUT_SECONDS = 90
DEFAULT_DRIVER_GENES = ["TP53", "KRAS", "EGFR", "STK11", "KEAP1", "BRAF", "MET", "ERBB2", "ALK", "RBM10", "NF1"]
NON_CODING_OR_SILENT = {
    "Silent",
    "Intron",
    "IGR",
    "3'UTR",
    "5'UTR",
    "3'Flank",
    "5'Flank",
    "RNA",
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def plan_downloads(manifest: dict) -> list[dict]:
    project_id = manifest.get("gdc_projects", ["TCGA-LUAD"])[0]
    return [
        {
            "provider": "tcga_gdc",
            "project_id": project_id,
            "endpoint": "https://api.gdc.cancer.gov/cases",
            "file": "tcga-luad_cases.json",
            "description": "TCGA-LUAD clinical case metadata",
        },
        {
            "provider": "tcga_gdc",
            "project_id": project_id,
            "endpoint": GDC_FILES_ENDPOINT,
            "file": "tcga-luad_masked_maf_files.json",
            "description": "GDC index of open masked somatic MAF files",
        },
        {
            "provider": "tcga_gdc",
            "project_id": project_id,
            "endpoint": GDC_DATA_ENDPOINT,
            "file": "tcga-luad_maf/*.maf.gz",
            "description": "Per-aliquot masked somatic mutation MAF files",
        },
    ]


def _request_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ClinicalRepBench-open-data-prep/0.3"},
    )
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return json.load(response)


def _write_download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ClinicalRepBench-open-data-prep/0.3"},
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        with temporary.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    temporary.replace(destination)
    return destination


def query_masked_maf_files(project_id: str, output_path: str | Path, size: int = 2000) -> dict:
    filters = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.project.project_id", "value": [project_id]}},
            {"op": "in", "content": {"field": "data_type", "value": ["Masked Somatic Mutation"]}},
            {"op": "in", "content": {"field": "data_format", "value": ["MAF"]}},
            {
                "op": "in",
                "content": {
                    "field": "analysis.workflow_type",
                    "value": ["Aliquot Ensemble Somatic Variant Merging and Masking"],
                },
            },
        ],
    }
    params = {
        "filters": json.dumps(filters),
        "fields": "file_id,file_name,file_size,data_type,data_format,experimental_strategy,analysis.workflow_type,cases.submitter_id",
        "format": "JSON",
        "size": str(size),
    }
    payload = _request_json(f"{GDC_FILES_ENDPOINT}?{urllib.parse.urlencode(params)}")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def _download_maf_chunk(items: list[dict], output_root: Path, chunk_index: int) -> None:
    ids = [item["file_id"] for item in items]
    request = urllib.request.Request(
        GDC_DATA_ENDPOINT,
        data=json.dumps({"ids": ids}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ClinicalRepBench-open-data-prep/0.3",
        },
    )
    archive_path = output_root / f"gdc_maf_chunk_{chunk_index:04d}.tar.gz.part"
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS * 4) as response:
        with archive_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)

    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith((".maf", ".maf.gz")):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            destination = output_root / Path(member.name).name
            with destination.open("wb") as handle:
                shutil.copyfileobj(extracted, handle)
    archive_path.unlink(missing_ok=True)


def download_masked_maf_files(file_index: dict, output_dir: str | Path, force: bool = False, chunk_size: int = 100) -> list[Path]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    items = list(file_index.get("data", {}).get("hits", []))
    missing = [item for item in items if force or not (output_root / item["file_name"]).exists()]
    for index in range(0, len(missing), chunk_size):
        _download_maf_chunk(missing[index : index + chunk_size], output_root, index // chunk_size)
    paths = [output_root / item["file_name"] for item in items if (output_root / item["file_name"]).exists()]
    return paths


def _read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_clinical_cases(path: str | Path) -> pd.DataFrame:
    payload = _read_json(path)
    rows: list[dict] = []
    for case in payload.get("data", {}).get("hits", []):
        diagnosis = (case.get("diagnoses") or [{}])[0]
        demographic = case.get("demographic") or {}
        exposure = (case.get("exposures") or [{}])[0]
        rows.append(
            {
                "case_id": case.get("case_id"),
                "patient_barcode": case.get("submitter_id"),
                "project_id": (case.get("project") or {}).get("project_id"),
                "primary_diagnosis": diagnosis.get("primary_diagnosis"),
                "tumor_stage": diagnosis.get("tumor_stage"),
                "age_at_diagnosis_days": diagnosis.get("age_at_diagnosis"),
                "vital_status": demographic.get("vital_status"),
                "gender": demographic.get("gender"),
                "race": demographic.get("race"),
                "days_to_death": diagnosis.get("days_to_death"),
                "days_to_last_follow_up": diagnosis.get("days_to_last_follow_up"),
                "tobacco_smoking_status": exposure.get("tobacco_smoking_status"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["event_death"] = frame["vital_status"].astype(str).str.lower().eq("dead").astype(int)
    frame["followup_days"] = pd.to_numeric(frame["days_to_death"], errors="coerce").fillna(
        pd.to_numeric(frame["days_to_last_follow_up"], errors="coerce")
    )
    frame["age_at_diagnosis_years"] = pd.to_numeric(frame["age_at_diagnosis_days"], errors="coerce") / 365.25
    return frame


def sequenced_patients_from_index(file_index: dict) -> set[str]:
    patients: set[str] = set()
    for item in file_index.get("data", {}).get("hits", []):
        for case in item.get("cases") or []:
            submitter_id = case.get("submitter_id")
            if submitter_id:
                patients.add(str(submitter_id)[:12])
    return patients


def read_maf(path: str | Path) -> pd.DataFrame:
    resolved = Path(path)
    opener = gzip.open if resolved.suffix == ".gz" else open
    with opener(resolved, "rt", encoding="utf-8", errors="replace") as handle:
        return pd.read_csv(handle, sep="\t", comment="#", low_memory=False)


def load_mutations(maf_dir: str | Path) -> pd.DataFrame:
    root = Path(maf_dir)
    paths = sorted([*root.glob("*.maf"), *root.glob("*.maf.gz")])
    frames: list[pd.DataFrame] = []
    for path in paths:
        frame = read_maf(path)
        if frame.empty:
            continue
        keep = [column for column in ["Hugo_Symbol", "Tumor_Sample_Barcode", "Variant_Classification"] if column in frame.columns]
        if len(keep) < 3:
            continue
        frames.append(frame[keep].copy())
    if not frames:
        return pd.DataFrame(columns=["Hugo_Symbol", "Tumor_Sample_Barcode", "Variant_Classification", "patient_barcode"])

    mutations = pd.concat(frames, ignore_index=True, sort=False)
    mutations["Hugo_Symbol"] = mutations["Hugo_Symbol"].astype(str).str.upper()
    mutations["patient_barcode"] = mutations["Tumor_Sample_Barcode"].astype(str).str.slice(0, 12)
    return mutations


def non_silent_mutations(mutations: pd.DataFrame) -> pd.DataFrame:
    if mutations.empty:
        return mutations.copy()
    classes = mutations["Variant_Classification"].astype(str)
    return mutations.loc[~classes.isin(NON_CODING_OR_SILENT)].copy()


def build_patient_matrix(clinical: pd.DataFrame, mutations: pd.DataFrame, sequenced_patients: set[str], driver_genes: list[str]) -> pd.DataFrame:
    data = clinical.loc[clinical["patient_barcode"].isin(sequenced_patients)].copy()
    data = data.drop_duplicates("patient_barcode").reset_index(drop=True)
    non_silent = non_silent_mutations(mutations)
    altered = non_silent.loc[non_silent["Hugo_Symbol"].isin(driver_genes), ["patient_barcode", "Hugo_Symbol"]].drop_duplicates()
    for gene in driver_genes:
        patients = set(altered.loc[altered["Hugo_Symbol"] == gene, "patient_barcode"])
        data[f"{gene}_mutated"] = data["patient_barcode"].isin(patients).astype(int)
    return data


def _pct(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return math.nan
    return round(float(numerator) / float(denominator) * 100.0, 4)


def build_driver_frequency_table(patient_matrix: pd.DataFrame, driver_genes: list[str]) -> pd.DataFrame:
    rows = []
    denominator = len(patient_matrix)
    for gene in driver_genes:
        column = f"{gene}_mutated"
        mutated_n = int(patient_matrix[column].sum()) if column in patient_matrix.columns else 0
        rows.append({"gene": gene, "mutated_n": mutated_n, "sequenced_patient_n": denominator, "mutated_pct": _pct(mutated_n, denominator)})
    return pd.DataFrame(rows)


def build_overlap_table(patient_matrix: pd.DataFrame) -> pd.DataFrame:
    egfr = patient_matrix.get("EGFR_mutated", pd.Series(dtype=int)).astype(bool)
    kras = patient_matrix.get("KRAS_mutated", pd.Series(dtype=int)).astype(bool)
    return pd.DataFrame(
        [
            {"group": "EGFR_only", "n": int((egfr & ~kras).sum())},
            {"group": "KRAS_only", "n": int((kras & ~egfr).sum())},
            {"group": "EGFR_KRAS_overlap", "n": int((egfr & kras).sum())},
            {"group": "Neither_EGFR_nor_KRAS", "n": int((~egfr & ~kras).sum())},
        ]
    )


def build_metrics(clinical: pd.DataFrame, patient_matrix: pd.DataFrame, mutations: pd.DataFrame, driver_freq: pd.DataFrame, overlap: pd.DataFrame) -> dict:
    sequenced_n = int(len(patient_matrix))
    non_silent_n = int(len(non_silent_mutations(mutations)))
    freq = {row["gene"]: row for row in driver_freq.to_dict("records")}
    overlap_map = dict(zip(overlap["group"], overlap["n"]))
    egfr_kras_altered = overlap_map.get("EGFR_only", 0) + overlap_map.get("KRAS_only", 0) + overlap_map.get("EGFR_KRAS_overlap", 0)
    return {
        "luad_case_n": int(len(clinical)),
        "sequenced_patient_n": sequenced_n,
        "non_silent_mutation_n": non_silent_n,
        "tp53_mutated_pct": float(freq.get("TP53", {}).get("mutated_pct", 0.0)),
        "kras_mutated_pct": float(freq.get("KRAS", {}).get("mutated_pct", 0.0)),
        "egfr_mutated_pct": float(freq.get("EGFR", {}).get("mutated_pct", 0.0)),
        "stk11_mutated_pct": float(freq.get("STK11", {}).get("mutated_pct", 0.0)),
        "keap1_mutated_pct": float(freq.get("KEAP1", {}).get("mutated_pct", 0.0)),
        "egfr_kras_overlap_n": int(overlap_map.get("EGFR_KRAS_overlap", 0)),
        "egfr_kras_exclusive_n": int(overlap_map.get("EGFR_only", 0) + overlap_map.get("KRAS_only", 0)),
        "egfr_kras_exclusive_pct_among_altered": _pct(
            overlap_map.get("EGFR_only", 0) + overlap_map.get("KRAS_only", 0),
            egfr_kras_altered,
        ),
        "death_event_pct": _pct(int(patient_matrix.get("event_death", pd.Series(dtype=int)).sum()), sequenced_n),
    }


def _write_bar_figure(path: Path, driver_freq: pd.DataFrame) -> None:
    top = driver_freq.head(8).copy()
    width = 760
    row_h = 28
    height = 80 + len(top) * row_h
    max_pct = max(float(top["mutated_pct"].max()), 1.0)
    rows = []
    for i, row in enumerate(top.to_dict("records")):
        y = 58 + i * row_h
        bar_w = float(row["mutated_pct"]) / max_pct * 430
        rows.append(
            f'<text x="24" y="{y + 16}" font-family="Arial" font-size="14">{row["gene"]}</text>'
            f'<rect x="110" y="{y}" width="{bar_w:.1f}" height="18" fill="#4C78A8"/>'
            f'<text x="{120 + bar_w:.1f}" y="{y + 15}" font-family="Arial" font-size="13">{row["mutated_pct"]:.1f}%</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="{width}" height="{height}" fill="white"/>'
        '<text x="24" y="32" font-family="Arial" font-size="20">TCGA-LUAD driver mutation frequencies</text>'
        + "".join(rows)
        + "</svg>\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def _write_report(workspace: Path, metrics: dict, driver_genes: list[str]) -> None:
    report = f"""# TCGA-LUAD Reference Report

## Methods

I reproduced the open-data component of PMID 25079552, the Nature 2014 TCGA study "Comprehensive molecular profiling of lung adenocarcinoma", using GDC TCGA-LUAD clinical cases and harmonized masked WXS somatic MAF files. The cohort was rebuilt from the GDC cases JSON, and the sequencing denominator was restricted to the intersection of TCGA-LUAD clinical patients and patients represented in the masked somatic MAF index or tumor barcodes. The patient-level driver matrix collapsed non-silent alterations to gene-level indicators for recurrent LUAD driver genes: {", ".join(driver_genes)}. Tumor stage was retained as the open-data proxy for the source paper's TNM frame, while follow-up and death-event fields were audited for survival endpoint availability.

## Re-Discovery

The reference run identified {metrics['sequenced_patient_n']} sequenced TCGA-LUAD patients and {metrics['non_silent_mutation_n']} non-silent mutation records. The leading driver frequencies were TP53 {metrics['tp53_mutated_pct']:.2f}%, KRAS {metrics['kras_mutated_pct']:.2f}%, EGFR {metrics['egfr_mutated_pct']:.2f}%, STK11 {metrics['stk11_mutated_pct']:.2f}%, and KEAP1 {metrics['keap1_mutated_pct']:.2f}%. EGFR/KRAS overlap was {metrics['egfr_kras_overlap_n']} patients, preserving the expected near-mutual-exclusion pattern for canonical LUAD oncogenic subtype separation. This reproduces the source paper's driver-gene directionality but not its full multi-platform molecular subtype taxonomy.

## New-Discovery

A compact clinical-genomic benchmark signal is the EGFR/KRAS exclusivity rate among patients altered in either gene. In this run, {metrics['egfr_kras_exclusive_pct_among_altered']:.2f}% of EGFR/KRAS-altered patients had exactly one of the two alterations. This is a bounded sensitivity check on molecular subtype separation rather than a clinical decision rule; no p-value or confidence interval should be interpreted as treatment evidence without validation.

## Results

The open clinical endpoint audit found death events in {metrics['death_event_pct']:.2f}% of the sequenced cohort. A full Kaplan-Meier or Cox proportional-hazards reproduction, including hazard ratio estimation, censoring diagnostics, and stage-adjusted/TNM-adjusted multivariable modeling, is not fully supported by this open masked-mutation-only scaffold. Table 3 therefore records survival availability, EGFR/KRAS overlap, and paper-alignment limitations rather than claiming a definitive prognostic model.

## Limitations

This public-data reference uses harmonized GDC masked somatic mutations rather than the exact 2014 multi-platform TCGA publication freeze. It does not recover all copy-number, methylation, RNA expression, fusion, proteomic, or legacy platform calls from the source paper. Survival fields have missingness, censoring assumptions are not audited beyond endpoint availability, and observational TCGA data remain vulnerable to confounding, selection bias, and limited generalizability.

## Clinical Safety

The outputs are cohort-level benchmark artifacts. Statistical significance, where calculated in downstream analyses, must be separated from clinical significance. These results are not suitable for individual treatment decisions, molecular tumor board recommendations, prognostication, or trial eligibility without validated clinical-grade testing and prospective clinical governance.
"""
    report_path = workspace / "report" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def _write_submission(workspace: Path) -> None:
    _write_json(
        workspace / "submission.json",
        {
            "submission_version": "0.1",
            "task_id": "Oncology_000",
            "report_path": "report/report.md",
            "metrics_path": "artifacts/primary_metrics.json",
            "artifacts": {
                "table1": "artifacts/tables/table1.csv",
                "table2": "artifacts/tables/table2.csv",
                "table3": "artifacts/tables/table3.csv",
                "figure1": "artifacts/figures/figure1.svg",
            },
        },
    )


def _write_analysis_code(workspace: Path) -> None:
    code = r'''from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


DRIVER_GENES = ["TP53", "KRAS", "EGFR", "STK11", "KEAP1", "BRAF", "MET", "ERBB2", "ALK", "RBM10", "NF1"]
EXCLUDED_CLASSES = {"Silent", "Intron", "IGR", "3'UTR", "5'UTR", "3'Flank", "5'Flank", "RNA"}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_cases(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text(encoding="utf-8"))
    hits = data.get("data", {}).get("hits", data if isinstance(data, list) else [])
    rows = []
    for case in hits:
        diagnoses = case.get("diagnoses") or [{}]
        diagnosis = diagnoses[0] if diagnoses else {}
        demographic = case.get("demographic") or {}
        submitter_id = case.get("submitter_id") or case.get("case_submitter_id")
        rows.append(
            {
                "case_id": case.get("case_id"),
                "patient_barcode": submitter_id,
                "vital_status": demographic.get("vital_status"),
                "tumor_stage": diagnosis.get("tumor_stage"),
                "days_to_death": diagnosis.get("days_to_death"),
                "days_to_last_follow_up": diagnosis.get("days_to_last_follow_up"),
                "gender": demographic.get("gender"),
                "race": demographic.get("race"),
            }
        )
    return pd.DataFrame(rows)


def load_index_patients(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    hits = data.get("data", {}).get("hits", data if isinstance(data, list) else [])
    patients = set()
    for item in hits:
        for case in item.get("cases", []) or []:
            submitter = case.get("submitter_id") or case.get("case_submitter_id")
            if submitter:
                patients.add(str(submitter)[:12])
    return patients


def load_mutations(maf_dir: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(maf_dir.glob("*.maf*")):
        frame = pd.read_csv(path, sep="\t", comment="#", dtype=str, compression="infer")
        required = ["Hugo_Symbol", "Tumor_Sample_Barcode", "Variant_Classification"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"{path} is missing columns: {missing}")
        frame = frame[required].copy()
        frame["patient_barcode"] = frame["Tumor_Sample_Barcode"].astype(str).str.slice(0, 12)
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["Hugo_Symbol", "Tumor_Sample_Barcode", "Variant_Classification", "patient_barcode"])
    return pd.concat(frames, ignore_index=True)


def pct(numerator: float, denominator: float) -> float:
    return round(float(numerator) / float(denominator) * 100.0, 4) if denominator else 0.0


def main() -> int:
    root = Path.cwd()
    source = root / "data" / "source"
    clinical = load_cases(source / "tcga-luad_cases.json")
    mutations = load_mutations(source / "tcga-luad_maf")
    non_silent = mutations[~mutations["Variant_Classification"].isin(EXCLUDED_CLASSES)].copy()

    sequenced = load_index_patients(source / "tcga-luad_masked_maf_files.json")
    sequenced.update(mutations["patient_barcode"].dropna().astype(str).unique())
    if not sequenced:
        sequenced.update(clinical["patient_barcode"].dropna().astype(str).unique())

    clinical_subset = clinical.drop_duplicates("patient_barcode")
    if not sequenced:
        sequenced.update(clinical_subset["patient_barcode"].dropna().astype(str).unique())
    matrix = clinical_subset.loc[clinical_subset["patient_barcode"].isin(sequenced)].copy().reset_index(drop=True)
    matrix["event_death"] = matrix["vital_status"].astype(str).str.lower().eq("dead").astype(int)
    for gene in DRIVER_GENES:
        altered_patients = set(
            non_silent.loc[
                non_silent["Hugo_Symbol"].astype(str).str.upper().eq(gene),
                "patient_barcode",
            ]
        )
        matrix[f"{gene}_mutated"] = matrix["patient_barcode"].isin(altered_patients).astype(int)

    sequenced_n = int(len(matrix))
    egfr = matrix["EGFR_mutated"].eq(1)
    kras = matrix["KRAS_mutated"].eq(1)
    egfr_kras_overlap_n = int((egfr & kras).sum())
    egfr_kras_exclusive_n = int((egfr ^ kras).sum())
    egfr_kras_altered_n = int((egfr | kras).sum())
    metrics = {
        "luad_case_n": int(len(clinical)),
        "sequenced_patient_n": sequenced_n,
        "non_silent_mutation_n": int(len(non_silent)),
        "tp53_mutated_pct": pct(matrix["TP53_mutated"].sum(), sequenced_n),
        "kras_mutated_pct": pct(matrix["KRAS_mutated"].sum(), sequenced_n),
        "egfr_mutated_pct": pct(matrix["EGFR_mutated"].sum(), sequenced_n),
        "stk11_mutated_pct": pct(matrix["STK11_mutated"].sum(), sequenced_n),
        "keap1_mutated_pct": pct(matrix["KEAP1_mutated"].sum(), sequenced_n),
        "egfr_kras_overlap_n": egfr_kras_overlap_n,
        "egfr_kras_exclusive_n": egfr_kras_exclusive_n,
        "egfr_kras_exclusive_pct_among_altered": pct(egfr_kras_exclusive_n, egfr_kras_altered_n),
        "death_event_pct": pct(matrix["event_death"].sum(), sequenced_n),
    }

    artifacts = root / "artifacts"
    tables = artifacts / "tables"
    figures = artifacts / "figures"
    report = root / "report"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    report.mkdir(parents=True, exist_ok=True)
    write_json(artifacts / "primary_metrics.json", {"metrics": metrics})
    pd.DataFrame(
        [
            {"measure": "GDC TCGA-LUAD clinical cases", "value": metrics["luad_case_n"]},
            {"measure": "Sequenced patients with masked somatic MAF", "value": metrics["sequenced_patient_n"]},
            {"measure": "Non-silent mutation records", "value": metrics["non_silent_mutation_n"]},
            {"measure": "Death event pct among sequenced patients", "value": metrics["death_event_pct"]},
        ]
    ).to_csv(tables / "table1.csv", index=False)
    pd.DataFrame(
        [
            {"gene": gene, "mutated_n": int(matrix[f"{gene}_mutated"].sum()), "mutated_pct": pct(matrix[f"{gene}_mutated"].sum(), sequenced_n)}
            for gene in DRIVER_GENES
        ]
    ).to_csv(tables / "table2.csv", index=False)
    pd.DataFrame(
        [
            {"analysis": "EGFR_only", "n": int((egfr & ~kras).sum()), "note": "EGFR/KRAS subtype separation"},
            {"analysis": "KRAS_only", "n": int((kras & ~egfr).sum()), "note": "EGFR/KRAS subtype separation"},
            {"analysis": "EGFR_KRAS_overlap", "n": egfr_kras_overlap_n, "note": "Expected to be uncommon"},
            {"analysis": "death_event_pct", "n": metrics["death_event_pct"], "note": "Survival endpoint availability"},
            {"analysis": "paper_alignment", "n": "", "note": "Open masked MAF scaffold cannot fully reproduce copy-number, methylation, RNA, fusion, or TNM-adjusted survival claims"},
        ]
    ).to_csv(tables / "table3.csv", index=False)
    rows = []
    max_pct = max(metrics["tp53_mutated_pct"], metrics["kras_mutated_pct"], metrics["egfr_mutated_pct"], 1.0)
    for index, gene in enumerate(["TP53", "KRAS", "EGFR", "STK11", "KEAP1"]):
        metric_id = f"{gene.lower()}_mutated_pct"
        y = 54 + index * 28
        width = metrics[metric_id] / max_pct * 360
        rows.append(
            f'<text x="20" y="{y + 15}" font-family="Arial" font-size="13">{gene}</text>'
            f'<rect x="90" y="{y}" width="{width:.1f}" height="18" fill="#4C78A8"/>'
            f'<text x="{100 + width:.1f}" y="{y + 15}" font-family="Arial" font-size="13">{metrics[metric_id]:.1f}%</text>'
        )
    (figures / "figure1.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="620" height="230">'
        '<rect width="620" height="230" fill="white"/>'
        '<text x="20" y="30" font-family="Arial" font-size="18">TCGA-LUAD driver mutation frequencies</text>'
        + "".join(rows)
        + "</svg>\n",
        encoding="utf-8",
    )
    (report / "report.md").write_text(
        f"""# TCGA-LUAD Molecular Profile Reproduction

## Methods
The analysis reproduced the open-data component of PMID 25079552, the Nature 2014 TCGA-LUAD study "Comprehensive molecular profiling of lung adenocarcinoma". It rebuilt a patient-level driver mutation matrix from raw GDC clinical JSON, the masked somatic MAF index, and raw `.maf`/`.maf.gz` files. The sequenced denominator was restricted to TCGA-LUAD clinical patients represented in the mutation data. Silent and non-coding variant classes were excluded before gene-level mutation indicators were derived, and tumor stage was retained as the available TNM proxy.

## Re-Discovery
The run recovered TP53 {metrics['tp53_mutated_pct']:.4f}%, KRAS {metrics['kras_mutated_pct']:.4f}%, EGFR {metrics['egfr_mutated_pct']:.4f}%, STK11 {metrics['stk11_mutated_pct']:.4f}%, and KEAP1 {metrics['keap1_mutated_pct']:.4f}% mutation frequencies. These markers support molecular subtype separation in the same direction as the source paper, while the open GDC scaffold cannot fully reconstruct its multi-platform subtype taxonomy.

## New-Discovery
EGFR/KRAS exclusivity among altered patients was {metrics['egfr_kras_exclusive_pct_among_altered']:.4f}%, a bounded sensitivity signal for canonical LUAD driver separation. This is not a clinical decision rule; p-value, confidence interval, or uncertainty estimates would require a prespecified validation analysis.

## Results
The cohort included {metrics['luad_case_n']} clinical cases and {metrics['sequenced_patient_n']} sequenced patients with {metrics['non_silent_mutation_n']} non-silent mutation records. Death events were available in {metrics['death_event_pct']:.4f}% of sequenced patients. A full Kaplan-Meier or Cox hazard ratio analysis with censoring diagnostics and stage-adjusted/TNM-adjusted multivariable modeling is not claimed from this open masked-mutation scaffold.

## Limitations
The workflow uses open harmonized GDC masked mutations and does not recover protected assays, copy-number calls, methylation profiles, RNA expression, fusion calls, or every legacy platform from the publication freeze. Missingness, observational confounding, selection bias, and limited generalizability remain explicit assumptions.

## Clinical Safety
These outputs are cohort-level benchmark artifacts. Statistical significance must be separated from clinical significance, and these results are not suitable for individual treatment decisions without validated clinical-grade assays.
""",
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
                "table3": "artifacts/tables/table3.csv",
                "figure1": "artifacts/figures/figure1.svg",
            },
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
    code_path = workspace / "code" / "analysis.py"
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text(code, encoding="utf-8")


def _source_paths(workspace: Path, cache_dir: str | Path | None) -> tuple[Path, Path, Path]:
    source_root = Path(cache_dir) if cache_dir is not None else workspace / "data" / "source"
    return (
        source_root / "tcga-luad_cases.json",
        source_root / "tcga-luad_masked_maf_files.json",
        source_root / "tcga-luad_maf",
    )


def prepare_luad_molecular_profile(
    manifest: dict,
    workspace: str | Path,
    cache_dir: str | Path | None = None,
    download: bool = False,
    force: bool = False,
) -> dict:
    workspace_root = Path(workspace)
    workspace_root.mkdir(parents=True, exist_ok=True)
    project_id = manifest.get("gdc_projects", ["TCGA-LUAD"])[0]
    driver_genes = [gene.upper() for gene in manifest.get("driver_genes", DEFAULT_DRIVER_GENES)]
    cases_path, index_path, maf_dir = _source_paths(workspace_root, cache_dir)

    fields = manifest.get(
        "fields",
        [
            "case_id",
            "submitter_id",
            "project.project_id",
            "diagnoses.primary_diagnosis",
            "diagnoses.tumor_stage",
            "diagnoses.days_to_death",
            "diagnoses.days_to_last_follow_up",
            "diagnoses.age_at_diagnosis",
            "demographic.vital_status",
            "demographic.gender",
            "demographic.race",
            "exposures.tobacco_smoking_status",
        ],
    )

    if download and (force or not cases_path.exists()):
        download_cases(project_id, cases_path, fields=fields)
    if download and (force or not index_path.exists()):
        query_masked_maf_files(project_id, index_path)
    if not cases_path.exists() or not index_path.exists():
        raise FileNotFoundError("Missing TCGA-LUAD clinical cases or masked MAF index; rerun with download=True")

    file_index = _read_json(index_path)
    if download:
        download_masked_maf_files(file_index, maf_dir, force=force)
    if not maf_dir.exists():
        raise FileNotFoundError("Missing TCGA-LUAD MAF directory; rerun with download=True")

    clinical = load_clinical_cases(cases_path)
    mutations = load_mutations(maf_dir)
    sequenced = sequenced_patients_from_index(file_index)
    sequenced.update(mutations["patient_barcode"].dropna().astype(str).unique())
    patient_matrix = build_patient_matrix(clinical, mutations, sequenced, driver_genes)
    driver_freq = build_driver_frequency_table(patient_matrix, driver_genes)
    overlap = build_overlap_table(patient_matrix)
    metrics = build_metrics(clinical, patient_matrix, mutations, driver_freq, overlap)

    data_dir = workspace_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    patient_matrix.to_csv(data_dir / "analytic_extract.csv", index=False)
    mutations.to_csv(data_dir / "mutation_extract.csv", index=False)

    artifacts = workspace_root / "artifacts"
    tables = artifacts / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    table1 = pd.DataFrame(
        [
            {"measure": "GDC TCGA-LUAD clinical cases", "value": metrics["luad_case_n"]},
            {"measure": "Sequenced patients with masked somatic MAF", "value": metrics["sequenced_patient_n"]},
            {"measure": "Non-silent mutation records", "value": metrics["non_silent_mutation_n"]},
            {"measure": "Death event pct among sequenced patients", "value": metrics["death_event_pct"]},
        ]
    )
    table1.to_csv(tables / "table1.csv", index=False)
    driver_freq.to_csv(tables / "table2.csv", index=False)
    overlap.to_csv(tables / "table3.csv", index=False)
    _write_bar_figure(artifacts / "figures" / "figure1.svg", driver_freq)
    _write_json(artifacts / "primary_metrics.json", {"metrics": metrics})
    _write_report(workspace_root, metrics, driver_genes)
    _write_analysis_code(workspace_root)
    _write_submission(workspace_root)

    return {
        "task_id": manifest["task_id"],
        "dataset": manifest["dataset"],
        "provider": manifest["provider"],
        "rows": int(len(patient_matrix)),
        "output_csv": str((data_dir / "analytic_extract.csv").resolve()),
        "metrics": metrics,
    }


def run_luad_reference(
    manifest: dict,
    workspace: str | Path,
    cache_dir: str | Path | None = None,
    download: bool = False,
    force: bool = False,
) -> dict:
    result = prepare_luad_molecular_profile(
        manifest=manifest,
        workspace=workspace,
        cache_dir=cache_dir,
        download=download,
        force=force,
    )
    return result["metrics"]
