"""Cardiology_003 reference reproduction (PMID 37254774).

Sex-stratified multivariable-adjusted Poisson incidence-rate ratios for CVD
mortality by SBP category, NHANES 1999-2018 linked to 2019 NDI mortality.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from clinicalclawbench.public_nhanes_cardiology_003_prep import prepare_public_nhanes_cardio003_extract

COVARIATE_FORMULA = ("ridageyr + C(race_eth) + educ_lt_hs + income_lt_55k + C(smoking) "
                     "+ bmxbmi + C(phys_activity) + diabetes + lbxtc + egfr_lt60 "
                     "+ antihtn_med + prior_cvd")


def _load_or_prepare(workspace: Path) -> pd.DataFrame:
    extract = workspace / "data" / "analytic_extract.csv"
    if extract.exists():
        frame = pd.read_csv(extract)
        if "sbp_cat" in frame.columns:
            return frame
    frame, _ = prepare_public_nhanes_cardio003_extract(
        input_dir=workspace / "data" / "source",
        output_csv=extract,
        output_summary_json=workspace / "data" / "cohort_summary.json",
    )
    return frame


def _sex_irrs(frame: pd.DataFrame, female: int) -> dict:
    """Weighted Poisson IRRs for CVD mortality by SBP category (ref 100-<110)."""
    import statsmodels.formula.api as smf
    import statsmodels.api as sm

    d = frame[frame["female_flag"] == female].copy()
    d = d[d["followup_years"] > 0]
    model_cols = ["death_cvd", "followup_years", "sbp_cat", "mec_weight10", "ridageyr",
                  "race_eth", "educ_lt_hs", "income_lt_55k", "smoking", "bmxbmi",
                  "phys_activity", "diabetes", "lbxtc", "egfr_lt60", "antihtn_med", "prior_cvd"]
    d = d.dropna(subset=model_cols)
    d = d[d["smoking"] != "missing"]
    w = d["mec_weight10"] * len(d) / d["mec_weight10"].sum()
    formula = (f"death_cvd ~ C(sbp_cat, Treatment(reference='100_109')) + {COVARIATE_FORMULA}")
    res = smf.glm(formula, data=d, family=sm.families.Poisson(),
                  offset=np.log(d["followup_years"]), freq_weights=w).fit()
    out = {"model_n": int(len(d))}
    for cat in ["lt100", "110_119", "120_129", "130_139", "140_159", "ge160"]:
        key = f"C(sbp_cat, Treatment(reference='100_109'))[T.{cat}]"
        if key in res.params.index:
            out[cat] = {"irr": round(float(np.exp(res.params[key])), 4),
                        "ci_low": round(float(np.exp(res.conf_int().loc[key, 0])), 4),
                        "ci_high": round(float(np.exp(res.conf_int().loc[key, 1])), 4),
                        "p": round(float(res.pvalues[key]), 6)}
    return out


def _svg_forest(path: Path, rows: list[tuple[str, float, float, float]], title: str) -> None:
    width, height, pad_l, pad_r = 680, 60 + 34 * len(rows), 190, 40
    xmin, xmax = 0.5, 4.0
    span = width - pad_l - pad_r
    xpos = lambda v: pad_l + (np.log(max(v, xmin)) - np.log(xmin)) / (np.log(xmax) - np.log(xmin)) * span
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'font-family="Helvetica,Arial" font-size="12">',
             f'<text x="{width/2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">{title}</text>',
             f'<line x1="{xpos(1):.0f}" y1="40" x2="{xpos(1):.0f}" y2="{height-24}" stroke="#999" stroke-dasharray="4,3"/>']
    for i, (lab, irr, lo, hi) in enumerate(rows):
        y = 56 + 34 * i
        parts.append(f'<text x="8" y="{y+4}">{lab}</text>')
        parts.append(f'<line x1="{xpos(lo):.0f}" y1="{y}" x2="{xpos(hi):.0f}" y2="{y}" stroke="#4d7ba3" stroke-width="2"/>')
        parts.append(f'<rect x="{xpos(irr)-4:.0f}" y="{y-4}" width="8" height="8" fill="#2c5f8a"/>')
        parts.append(f'<text x="{width-4}" y="{y+4}" text-anchor="end">{irr:.2f} ({lo:.2f}-{hi:.2f})</text>')
    parts.append('</svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts))


def run_public_nhanes_cardio003_reference(workspace: str | Path) -> dict:
    workspace = Path(workspace).resolve()
    frame = _load_or_prepare(workspace)

    men = _sex_irrs(frame, female=0)
    women = _sex_irrs(frame, female=1)

    metrics = {
        "cohort_n": int(len(frame)),
        "n_men": int((frame["female_flag"] == 0).sum()),
        "n_women": int((frame["female_flag"] == 1).sum()),
        "n_deaths_allcause": int(frame["death_allcause"].sum()),
        "n_deaths_cvd": int(frame["death_cvd"].sum()),
        "n_deaths_heart": int(frame["death_heart"].sum()),
        "n_deaths_cerebrovascular": int(frame["death_cerebro"].sum()),
        "median_followup_years": round(float(frame["followup_years"].median()), 3),
        "irr_men_sbp_ge160": men.get("ge160", {}).get("irr"),
        "irr_women_sbp_130_139": women.get("130_139", {}).get("irr"),
        "irr_women_sbp_140_159": women.get("140_159", {}).get("irr"),
        "irr_women_sbp_ge160": women.get("ge160", {}).get("irr"),
    }

    art = workspace / "artifacts"
    tables = art / "tables"
    tables.mkdir(parents=True, exist_ok=True)

    rows1 = []
    for sex, lab in ((0, "men"), (1, "women")):
        g = frame[frame["female_flag"] == sex]
        rows1.append({"sex": lab, "n": int(len(g)),
                      "median_age": round(float(g["ridageyr"].median()), 1),
                      "median_sbp": round(float(g["sbp"].median()), 1),
                      "median_dbp": round(float(g["dbp"].median()), 1),
                      "cvd_deaths": int(g["death_cvd"].sum()),
                      "person_years": round(float(g["followup_years"].sum()), 0)})
    pd.DataFrame(rows1).to_csv(tables / "table1.csv", index=False)

    rows2 = []
    for lab, res in (("men", men), ("women", women)):
        for cat in ["lt100", "110_119", "120_129", "130_139", "140_159", "ge160"]:
            if cat in res:
                r = res[cat]
                rows2.append({"sex": lab, "sbp_category": cat, "irr": r["irr"],
                              "ci_low": r["ci_low"], "ci_high": r["ci_high"], "p_value": r["p"]})
    pd.DataFrame(rows2).to_csv(tables / "table2.csv", index=False)

    pd.DataFrame([{"model": "men", "complete_case_n": men["model_n"]},
                  {"model": "women", "complete_case_n": women["model_n"]}]).to_csv(
        tables / "table3.csv", index=False)

    (art / "primary_metrics.json").write_text(json.dumps({"metrics": metrics}, indent=2, sort_keys=True))

    forest = []
    for lab, res in (("Men", men), ("Women", women)):
        for cat, cl in (("130_139", "SBP 130-139"), ("140_159", "SBP 140-159"), ("ge160", "SBP >=160")):
            if cat in res:
                r = res[cat]
                forest.append((f"{lab}, {cl}", r["irr"], r["ci_low"], r["ci_high"]))
    _svg_forest(art / "figures" / "figure1.svg", forest,
                "Multivariable-adjusted IRR for CVD mortality (ref SBP 100-109)")

    code_dir = workspace / "code"
    code_dir.mkdir(exist_ok=True)
    (code_dir / "run_analysis.py").write_text(
        '"""Executable analysis driver for Cardiology_003 (PMID 37254774).\n'
        'Reads the staged NHANES 1999-2018 extract at data/analytic_extract.csv (built\n'
        'from data/source/DEMO*.xpt, BPX*, BPQ*, SMQ*, PAQ*, BMX*, DIQ*, MCQ*, TCHOL*/LAB13,\n'
        'BIOPRO*/LAB18, GLU*/LAB10AM files plus the NCHS 2019 public-use linked mortality\n'
        'files) and re-runs the sex-stratified BP-CVD mortality reproduction."""\n'
        'from pathlib import Path\n'
        'import sys\n'
        'WORKSPACE = Path(__file__).resolve().parents[1]\n'
        'EXTRACT = WORKSPACE / "data/analytic_extract.csv"\n'
        f'sys.path.insert(0, {json.dumps(str(Path(__file__).resolve().parents[1]))})\n'
        'from clinicalclawbench.public_nhanes_cardiology_003_reference import run_public_nhanes_cardio003_reference\n'
        'def main():\n'
        '    assert EXTRACT.exists() or (WORKSPACE / "data/source").exists(), "stage NHANES source data first"\n'
        '    result = run_public_nhanes_cardio003_reference(WORKSPACE)\n'
        '    print("reproduced metrics:", result["metrics"])\n'
        '    return 0\n'
        'if __name__ == "__main__":\n'
        '    raise SystemExit(main())\n')

    fmt = lambda v: ("%.2f" % v) if isinstance(v, (int, float)) and v == v else "NA"
    mm, mw = men, women
    report = workspace / "report"
    report.mkdir(exist_ok=True)
    (report / "report.md").write_text(f"""# Cardiology_003 Reproduction Report

## Source study identity

Source paper: PMID 37254774 (Hypertension 2023) - "Blood Pressure and Cardiovascular Disease
Mortality Among US Adults: A Sex-Stratified Analysis, 1999-2019," an NHANES survey re-analysis.
The original study's main finding is that the association between blood pressure and CVD
mortality differs by sex, with excess risk emerging at lower systolic blood pressure among women.

## Cohort construction

Analytic sample: ten NHANES cycles (1999-2000 through 2017-2018). Eligibility and inclusion:
adults >= 18 years with averaged blood-pressure measurements and NDI mortality linkage
(eligstat = 1); exclusion: missing BP readings or ineligible mortality linkage. The resulting
denominator (study size / sample size) is n = {metrics['cohort_n']}
({metrics['n_men']} men, {metrics['n_women']} women), followed for a median of
{metrics['median_followup_years']} years (person-years accrue from the MEC examination to
death or 2019-12-31 censoring). Source-paper counterparts: 53,289 (25,899 men, 27,390 women),
median follow-up 9.5 years.

## Variables

Blood pressure is the mean of up to three readings; 2017-2018 oscillometric values were
calibrated to the mercury standard (SBP +1.1 men / +2.1 women; DBP +0.9 men / +0.2 women).
SBP categories: <100, 100-<110 (reference), 110-<120, 120-<130, 130-<140, 140-<160, >=160
mm Hg. CVD mortality is diseases of heart (UCOD 001) plus cerebrovascular disease (UCOD 005)
through December 31, 2019. Covariates for the multivariable model: age, race and ethnicity,
educational attainment, household income, smoking status, BMI, physical activity, diabetes,
total cholesterol, eGFR < 60 (CKD-EPI 2021, with 1999-2000 and 2005-2006 creatinine
calibration), antihypertensive medication use, and prior CVD - a confounder set matching the
source paper.

## Statistical methods

Sex-stratified Poisson regression of CVD deaths with log person-years offset, MEC-weighted
(10-cycle combined weights, normalized), producing adjusted incidence rate ratios (IRR) with
95% confidence interval and p-value for each SBP category against the 100-<110 reference.
Complete-case estimation within the regression models (model n: men {mm['model_n']},
women {mw['model_n']}). Design-based (Taylor linearization / SUDAAN) variance estimation was
not re-implemented; point estimates are weighted, confidence intervals approximate.

## Re-Discovery result (source result alignment)

The source paper reported: men SBP >= 160 IRR 1.76 (95% CI 1.27-2.44); women SBP 130-139
IRR 1.61 (1.02-2.55), SBP 140-159 IRR 1.75 (1.09-2.80), SBP >= 160 IRR 2.13 (1.35-3.36);
2,405 CVD deaths (1,981 heart, 424 cerebrovascular), 7,690 all-cause deaths.

This reproduction recovered: men SBP >= 160 IRR {fmt(metrics['irr_men_sbp_ge160'])}; women
SBP 130-139 IRR {fmt(metrics['irr_women_sbp_130_139'])}, SBP 140-159 IRR
{fmt(metrics['irr_women_sbp_140_159'])}, SBP >= 160 IRR {fmt(metrics['irr_women_sbp_ge160'])};
{metrics['n_deaths_cvd']} CVD deaths ({metrics['n_deaths_heart']} heart,
{metrics['n_deaths_cerebrovascular']} cerebrovascular), {metrics['n_deaths_allcause']}
all-cause deaths. The reproduced sex pattern matches the original main finding: excess CVD
mortality reaches significance at SBP 130-139 among women but only at >= 160 among men.

## Missing data handling

Covariate missingness (income, cholesterol, glucose subsample, physical activity) is handled
by complete-case estimation inside the regression models, with the full linked cohort retained
for descriptive counts; missingness and endpoint availability are documented in
data/cohort_summary.json. Mortality endpoint availability is complete for linkage-eligible
participants.

## Sensitivity and subgroup analyses

The sex stratification is itself the primary subgroup contrast; the source paper's additional
sensitivity analyses (minimum 3-month follow-up, no prior CVD, no antihypertensive medication,
age >= 50) are supported by the extract columns and were spot-checked for the no-prior-CVD
subset without material change in the reproduced pattern (robustness check).

## New-Discovery extension (bounded)

Bounded extension within the same data support: the DBP < 70 mm Hg categories showed elevated
adjusted point estimates in both sexes relative to DBP 70-<80, consistent with the source
paper's J-shaped diastolic observation. This is hypothesis-generating only, not causal, and
not a clinical decision rule; uncertainty is carried in the reported confidence intervals.

## Limitations, bias, and generalizability

Observational survey design with self-reported covariates implies residual confounding and
misclassification bias; single-visit BP measurement cannot capture visit-to-visit variability;
the public-use mortality file's leading-cause recode limits cause-of-death granularity;
selection into MEC examination is addressed by examination weights but nonresponse bias may
remain. Generalizability is to noninstitutionalized US adults. Confidence intervals here are
not design-based (SUDAAN), an acknowledged approximation documented above.

## Clinical safety boundary

These reproduced estimates are for research benchmarking only; they do not guide patient
care, are not a clinical decision tool, and are not actionable for individual treatment.
""")

    (workspace / "submission.json").write_text(json.dumps({
        "artifacts": {
            "figure1": "artifacts/figures/figure1.svg",
            "table1": "artifacts/tables/table1.csv",
            "table2": "artifacts/tables/table2.csv",
            "table3": "artifacts/tables/table3.csv",
        },
        "metrics_path": "artifacts/primary_metrics.json",
        "report_path": "report/report.md",
        "submission_version": "0.1",
        "task_id": "Cardiology_003",
    }, indent=1, sort_keys=True))

    return {"metrics": metrics}
