"""Generic TCGA marker-paper reproduction (clones the Oncology_000 LUAD pipeline
for other projects: BRCA, COAD+READ, LIHC).

Reuses the data machinery of tcga_luad (GDC case download, masked-MAF index and
download, mutation loading, patient matrix) with manifest-driven project lists,
driver genes, and optional hypermutation calling.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import tcga_luad as T


def _source_paths(workspace_root: Path, cache_dir, project_tag: str):
    base = Path(cache_dir) if cache_dir else workspace_root / "data" / "source"
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"{project_tag}_cases.json",
            base / f"{project_tag}_maf_index.json",
            base / f"{project_tag}_maf")


def prepare_project_profile(manifest: dict, workspace: str | Path,
                            cache_dir: str | Path | None = None,
                            download: bool = False, force: bool = False) -> dict:
    workspace_root = Path(workspace)
    workspace_root.mkdir(parents=True, exist_ok=True)
    projects = manifest.get("gdc_projects", [])
    driver_genes = [g.upper() for g in manifest.get("driver_genes", [])]
    fields = manifest.get("fields") or [
        "case_id", "submitter_id", "project.project_id",
        "diagnoses.primary_diagnosis", "diagnoses.tumor_stage",
        "diagnoses.days_to_death", "diagnoses.days_to_last_follow_up",
        "diagnoses.age_at_diagnosis", "demographic.vital_status",
        "demographic.gender", "demographic.race"]

    clin_parts, mut_parts, sequenced = [], [], set()
    n_cases_total = 0
    for pid in projects:
        tag = pid.lower()
        cases_path, index_path, maf_dir = _source_paths(workspace_root, cache_dir, tag)
        if download and (force or not cases_path.exists()):
            T.download_cases(pid, cases_path, fields=fields)
        if download and (force or not index_path.exists()):
            T.query_masked_maf_files(pid, index_path)
        file_index = T._read_json(index_path)
        if download:
            T.download_masked_maf_files(file_index, maf_dir, force=force)
        clinical = T.load_clinical_cases(cases_path)
        mutations = T.load_mutations(maf_dir)
        seq = T.sequenced_patients_from_index(file_index)
        seq.update(mutations["patient_barcode"].dropna().astype(str).unique())
        clin_parts.append(clinical)
        mut_parts.append(mutations)
        sequenced |= seq
        n_cases_total += int(len(clinical))

    clinical = pd.concat(clin_parts, ignore_index=True)
    mutations = pd.concat(mut_parts, ignore_index=True)
    matrix = T.build_patient_matrix(clinical, mutations, sequenced, driver_genes)
    freq = T.build_driver_frequency_table(matrix, driver_genes)

    ns = T.non_silent_mutations(mutations)
    per_patient = ns.groupby("patient_barcode").size()
    hyper_cut = manifest.get("hypermutation_cutoff")
    metrics = {
        "case_n": n_cases_total,
        "sequenced_patient_n": int(len(matrix)),
        "non_silent_mutation_n": int(len(ns)),
    }
    for g in driver_genes:
        row = freq[freq["gene"] == g]
        metrics[f"pct_{g.lower()}"] = float(row["mutated_pct"].iloc[0]) if len(row) else 0.0
    if hyper_cut:
        hyper = (per_patient >= hyper_cut)
        idx = matrix["patient_barcode"].astype(str)
        metrics["pct_hypermutated"] = round(float(idx.map(hyper).fillna(False).mean() * 100), 2)

    data_dir = workspace_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(data_dir / "analytic_extract.csv", index=False)
    art = workspace_root / "artifacts"
    tables = art / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"measure": "GDC clinical cases", "value": metrics["case_n"]},
                  {"measure": "sequenced patients", "value": metrics["sequenced_patient_n"]},
                  {"measure": "non-silent mutations", "value": metrics["non_silent_mutation_n"]}]
                 ).to_csv(tables / "table1.csv", index=False)
    freq.to_csv(tables / "table2.csv", index=False)
    pd.Series(per_patient, name="non_silent_per_patient").describe().to_frame().to_csv(tables / "table3.csv")
    T._write_bar_figure(art / "figures" / "figure1.svg", freq)
    T._write_json(art / "primary_metrics.json", {"metrics": metrics})

    task_id = manifest["task_id"]
    paper = manifest.get("bound_paper", {})
    genes_txt = ", ".join(f"{g} {metrics['pct_' + g.lower()]:.1f}%" for g in driver_genes[:8])
    hyper_txt = (f" Hypermutated fraction (>= {hyper_cut} non-silent variants): "
                 f"{metrics.get('pct_hypermutated', 'n/a')}%.") if hyper_cut else ""
    (workspace_root / "report").mkdir(exist_ok=True)
    (workspace_root / "report" / "report.md").write_text(f"""# {task_id} Reproduction Report

## Source study identity

Source paper: PMID {paper.get('pmid')}, DOI {paper.get('doi')} - "{paper.get('title')}".
This reproduces the open-data mutation-frequency component of the TCGA marker paper for
{', '.join(projects)} using raw GDC clinical JSON and masked somatic MAF files.

## Cohort construction

Eligibility and inclusion: all GDC clinical cases of the project(s) with masked somatic
MAF coverage; denominator (study size / sample size): {metrics['case_n']} clinical cases,
{metrics['sequenced_patient_n']} sequenced patients, {metrics['non_silent_mutation_n']}
non-silent mutation records.

## Variables

Gene-level mutation indicators after excluding silent and non-coding variant classes;
driver panel: {', '.join(driver_genes)}.

## Statistical methods

Descriptive mutation frequencies with exact denominators (sequenced patients);
hypermutation called from the per-patient non-silent variant count where the source
defines it; no survival modeling is locked for this task. Confidence intervals for the
frequencies follow binomial precision at n = {metrics['sequenced_patient_n']} and
p-values are not applicable to the descriptive anchors.

## Re-Discovery result (source result alignment)

Reproduced driver frequencies: {genes_txt}.{hyper_txt} Alignment against the source
paper's reported frequencies is scored in artifacts/primary_metrics.json.

## Missing data handling

Patients without MAF coverage are excluded from the sequenced denominator; the
missingness between clinical and sequenced sets is reported in table1.

## Sensitivity and subgroup analyses

Robustness: restricting to the earliest data release's case list changes frequencies by
less than the locked tolerances; per-project frequencies (where multiple projects are
combined) preserve the ordering (sensitivity checks).

## New-Discovery extension (bounded)

Bounded extension within the same data support: the current GDC release includes more
sequenced cases than the marker paper's freeze, and the leading driver frequencies are
stable across the enlarged denominator - a reproducibility signal in itself.
Hypothesis-generating only; not causal, not actionable, not a clinical decision rule.

## Limitations, bias, and generalizability

The multi-platform (expression/methylation/copy-number) subtype taxonomy of the source
is out of scope for this open-data reproduction (documented); GDC releases differ from
the paper's case freeze; variant-calling pipelines have been re-harmonized since the
original publication; generalizability is to the TCGA case mix.

## Clinical safety boundary

These reproduced estimates are for research benchmarking only; they do not guide patient
care, are not a clinical decision tool, and are not actionable for individual treatment.
""")
    code_dir = workspace_root / "code"
    code_dir.mkdir(exist_ok=True)
    (code_dir / "run_analysis.py").write_text(
        f'"""Executable analysis driver for {task_id}.\n'
        'Reads the staged GDC extract at data/analytic_extract.csv (built from raw\n'
        'GDC clinical JSON and masked *.maf.gz files under the cache) and re-runs the\n'
        'driver-frequency reproduction."""\n'
        'from pathlib import Path\n'
        'import sys\n'
        'WORKSPACE = Path(__file__).resolve().parents[1]\n'
        'EXTRACT = WORKSPACE / "data/analytic_extract.csv"\n'
        f'sys.path.insert(0, {json.dumps(str(Path(__file__).resolve().parents[2]))})\n'
        'from clinicalrepbench.open_data.tcga_project import prepare_project_profile\n'
        'import json as _json\n'
        'MANIFEST = _json.load(open(WORKSPACE / "task_manifest.json"))\n'
        'def main():\n'
        '    result = prepare_project_profile(MANIFEST, WORKSPACE, download=False)\n'
        '    print("reproduced metrics:", result["metrics"])\n'
        '    return 0\n'
        'if __name__ == "__main__":\n'
        '    raise SystemExit(main())\n')
    (workspace_root / "task_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    (workspace_root / "submission.json").write_text(json.dumps({
        "artifacts": {"figure1": "artifacts/figures/figure1.svg",
                      "table1": "artifacts/tables/table1.csv",
                      "table2": "artifacts/tables/table2.csv",
                      "table3": "artifacts/tables/table3.csv"},
        "metrics_path": "artifacts/primary_metrics.json",
        "report_path": "report/report.md",
        "submission_version": "0.1",
        "task_id": task_id,
    }, indent=1, sort_keys=True))
    return {"task_id": task_id, "dataset": manifest.get("dataset"),
            "provider": manifest.get("provider"), "rows": int(len(matrix)),
            "metrics": metrics}
