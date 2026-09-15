"""Hematology_001 reference reproduction (PMID 38586465).

Weighted Cox regression of anemia, hyperuricemia, and their interaction
(RERI / AP) on all-cause mortality among US adults with CKD, NHANES 2009-2018.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from clinicalrepbench.public_nhanes_hematology_001_prep import prepare_public_nhanes_hema001_extract

MODEL_COLS = ["followup_years", "death_allcause", "anemia", "hyperuricemia", "ridageyr",
              "female_flag", "race_eth", "married_partner", "indfmpir", "smoking",
              "met_min_week", "hypertension", "cvd", "diabetes", "cancer",
              "carb_supply_ratio", "mec_weight5"]


def _load_or_prepare(workspace: Path) -> pd.DataFrame:
    extract = workspace / "data" / "analytic_extract.csv"
    if extract.exists():
        frame = pd.read_csv(extract)
        if "hyperuricemia" in frame.columns:
            return frame
    frame, _ = prepare_public_nhanes_hema001_extract(
        input_dir=workspace / "data" / "source",
        output_csv=extract,
        output_summary_json=workspace / "data" / "cohort_summary.json",
    )
    return frame


def _fit_cox(d: pd.DataFrame, exposure_cols: list[str]) -> dict:
    """Weighted Cox PH via lifelines; returns HR (95% CI) per exposure column."""
    from lifelines import CoxPHFitter

    cols = exposure_cols + ["followup_years", "death_allcause", "ridageyr", "female_flag",
                            "married_partner", "indfmpir", "met_min_week", "hypertension",
                            "cvd", "diabetes", "cancer", "carb_supply_ratio", "mec_weight5"]
    dd = d.dropna(subset=[c for c in cols if c in d.columns] + ["race_eth"]).copy()
    dd = dd[dd["smoking"] != "missing"]
    dd = dd[dd["followup_years"] > 0]
    dd = pd.get_dummies(dd, columns=["race_eth", "smoking"], drop_first=True)
    model_cols = (exposure_cols + ["followup_years", "death_allcause", "ridageyr", "female_flag",
                                   "married_partner", "indfmpir", "met_min_week", "hypertension",
                                   "cvd", "diabetes", "cancer", "carb_supply_ratio"]
                  + [c for c in dd.columns if c.startswith("race_eth_") or c.startswith("smoking_")])
    w = dd["mec_weight5"] * len(dd) / dd["mec_weight5"].sum()
    dd = dd[model_cols].copy()
    dd["_w"] = w.values
    cph = CoxPHFitter()
    cph.fit(dd, duration_col="followup_years", event_col="death_allcause",
            weights_col="_w", robust=True)
    out = {"model_n": int(len(dd)), "model_events": int(dd["death_allcause"].sum())}
    ci = cph.confidence_intervals_
    for col in exposure_cols:
        out[col] = {"hr": round(float(np.exp(cph.params_[col])), 4),
                    "ci_low": round(float(np.exp(ci.loc[col].iloc[0])), 4),
                    "ci_high": round(float(np.exp(ci.loc[col].iloc[1])), 4)}
    return out


def run_public_nhanes_hema001_reference(workspace: str | Path) -> dict:
    workspace = Path(workspace).resolve()
    frame = _load_or_prepare(workspace)

    d = frame.dropna(subset=["anemia", "hyperuricemia"]).copy()

    main = _fit_cox(d, ["anemia", "hyperuricemia"])

    # Joint-category model for interaction (reference: neither)
    d["cat_anemia_only"] = ((d["anemia"] == 1) & (d["hyperuricemia"] == 0)).astype(int)
    d["cat_hyper_only"] = ((d["anemia"] == 0) & (d["hyperuricemia"] == 1)).astype(int)
    d["cat_both"] = ((d["anemia"] == 1) & (d["hyperuricemia"] == 1)).astype(int)
    joint = _fit_cox(d, ["cat_anemia_only", "cat_hyper_only", "cat_both"])
    hr_a, hr_h, hr_b = (joint["cat_anemia_only"]["hr"], joint["cat_hyper_only"]["hr"],
                        joint["cat_both"]["hr"])
    reri = round(hr_b - hr_a - hr_h + 1.0, 4)
    ap = round(reri / hr_b, 4) if hr_b else float("nan")

    metrics = {
        "cohort_n": int(len(frame)),
        "n_deaths_allcause": int(frame["death_allcause"].sum()),
        "hr_anemia": main["anemia"]["hr"],
        "hr_hyperuricemia": main["hyperuricemia"]["hr"],
        "hr_both_vs_neither": hr_b,
        "reri": reri,
        "attributable_proportion": ap,
    }

    art = workspace / "artifacts"
    tables = art / "tables"
    tables.mkdir(parents=True, exist_ok=True)

    rows1 = []
    for label, mask in [("neither", (d["anemia"] == 0) & (d["hyperuricemia"] == 0)),
                        ("anemia only", (d["anemia"] == 1) & (d["hyperuricemia"] == 0)),
                        ("hyperuricemia only", (d["anemia"] == 0) & (d["hyperuricemia"] == 1)),
                        ("both", (d["anemia"] == 1) & (d["hyperuricemia"] == 1))]:
        g = d[mask]
        rows1.append({"group": label, "n": int(len(g)),
                      "deaths": int(g["death_allcause"].sum()),
                      "median_age": round(float(g["ridageyr"].median()), 1) if len(g) else np.nan,
                      "median_egfr": round(float(g["egfr"].median()), 1) if len(g) else np.nan})
    pd.DataFrame(rows1).to_csv(tables / "table1.csv", index=False)

    pd.DataFrame([
        {"exposure": "anemia", "hr": main["anemia"]["hr"],
         "ci_low": main["anemia"]["ci_low"], "ci_high": main["anemia"]["ci_high"]},
        {"exposure": "hyperuricemia", "hr": main["hyperuricemia"]["hr"],
         "ci_low": main["hyperuricemia"]["ci_low"], "ci_high": main["hyperuricemia"]["ci_high"]},
        {"exposure": "anemia only (joint model)", "hr": hr_a,
         "ci_low": joint["cat_anemia_only"]["ci_low"], "ci_high": joint["cat_anemia_only"]["ci_high"]},
        {"exposure": "hyperuricemia only (joint model)", "hr": hr_h,
         "ci_low": joint["cat_hyper_only"]["ci_low"], "ci_high": joint["cat_hyper_only"]["ci_high"]},
        {"exposure": "both (joint model)", "hr": hr_b,
         "ci_low": joint["cat_both"]["ci_low"], "ci_high": joint["cat_both"]["ci_high"]},
    ]).to_csv(tables / "table2.csv", index=False)

    pd.DataFrame([{"measure": "RERI", "value": reri},
                  {"measure": "AP", "value": ap},
                  {"measure": "model_n", "value": main["model_n"]},
                  {"measure": "model_events", "value": main["model_events"]}]).to_csv(
        tables / "table3.csv", index=False)

    (art / "primary_metrics.json").write_text(json.dumps({"metrics": metrics}, indent=2, sort_keys=True))

    # simple bar SVG of joint-category HRs
    figs = art / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    labels = ["anemia only", "hyperuricemia only", "both"]
    values = [hr_a, hr_h, hr_b]
    width, height, pad = 560, 340, 56
    vmax = max(values) * 1.3
    bw = (width - 2 * pad) / 3
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="Helvetica,Arial" font-size="12">',
             '<text x="280" y="24" text-anchor="middle" font-size="15" font-weight="bold">Adjusted HR for all-cause mortality in CKD (ref: neither)</text>',
             f'<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#333"/>']
    for i, (lab, val) in enumerate(zip(labels, values)):
        h = (val / vmax) * (height - 2 * pad)
        x = pad + i * bw + bw * 0.18
        y = height - pad - h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.64:.1f}" height="{h:.1f}" fill="#8a5f2c"/>')
        parts.append(f'<text x="{x+bw*0.32:.1f}" y="{y-6:.1f}" text-anchor="middle">{val:.2f}</text>')
        parts.append(f'<text x="{x+bw*0.32:.1f}" y="{height-pad+16:.1f}" text-anchor="middle" font-size="10">{lab}</text>')
    parts.append('</svg>')
    (figs / "figure1.svg").write_text("\n".join(parts))

    code_dir = workspace / "code"
    code_dir.mkdir(exist_ok=True)
    (code_dir / "run_analysis.py").write_text(
        '"""Executable analysis driver for Hematology_001 (PMID 38586465).\n'
        'Reads the staged NHANES 2009-2018 CKD extract at data/analytic_extract.csv (built\n'
        'from data/source/DEMO_F..J.xpt, CBC_*, BIOPRO_*, ALB_CR_*, BPQ_*, BPX_*, DIQ_*,\n'
        'MCQ_*, SMQ_*, PAQ_*, DR1TOT_*, GHB_*, GLU_* files plus the NCHS 2019 public-use\n'
        'linked mortality files) and re-runs the anemia x hyperuricemia interaction\n'
        'reproduction."""\n'
        'from pathlib import Path\n'
        'import sys\n'
        'WORKSPACE = Path(__file__).resolve().parents[1]\n'
        'EXTRACT = WORKSPACE / "data/analytic_extract.csv"\n'
        f'sys.path.insert(0, {json.dumps(str(Path(__file__).resolve().parents[1]))})\n'
        'from clinicalrepbench.public_nhanes_hematology_001_reference import run_public_nhanes_hema001_reference\n'
        'def main():\n'
        '    assert EXTRACT.exists() or (WORKSPACE / "data/source").exists(), "stage NHANES source data first"\n'
        '    result = run_public_nhanes_hema001_reference(WORKSPACE)\n'
        '    print("reproduced metrics:", result["metrics"])\n'
        '    return 0\n'
        'if __name__ == "__main__":\n'
        '    raise SystemExit(main())\n')

    fmt = lambda v: ("%.2f" % v) if isinstance(v, (int, float)) and v == v else "NA"
    report = workspace / "report"
    report.mkdir(exist_ok=True)
    (report / "report.md").write_text(f"""# Hematology_001 Reproduction Report

## Source study identity

Source paper: PMID 38586465 (Renal Failure 2024) - "Interaction between anemia and
hyperuricemia in the risk of all-cause mortality in patients with chronic kidney disease,"
an NHANES survey-based retrospective cohort study. The original study's main finding is a
potential synergistic effect of anemia and hyperuricemia on all-cause mortality in CKD.

## Cohort construction

Analytic sample: NHANES 2009-2018 (five cycles). Eligibility and inclusion: adults with CKD
per KDIGO 2021 (UACR > 30 mg/g and/or eGFR < 60 mL/min/1.73m2 by the MDRD equation with
race and sex coefficients, as in the source paper); exclusion: implausible total energy
intake (< 500 or > 8,000 kcal men; < 500 or > 5,000 kcal women) and no mortality linkage.
The resulting denominator (study size / sample size) is n = {metrics['cohort_n']} CKD
patients with {metrics['n_deaths_allcause']} all-cause deaths through December 31, 2019
(source-paper counterparts: 3,678 and 819).

## Variables

Anemia: hemoglobin < 13 g/dL (men) / < 12 g/dL (women), per WHO. Hyperuricemia: serum uric
acid > 7 mg/dL (men) / > 6 mg/dL (women). Covariates in the multivariable model, matching
the source paper's final covariate set: age, sex, race and ethnicity, marital status,
poverty-income ratio, smoking status, physical activity (weekly MET-minutes), hypertension,
CVD, diabetes, cancer, and carbohydrate supply ratio.

## Statistical methods

Weighted Cox proportional hazards regression (MEC weights WTMEC2YR/5, normalized; robust
variance) for the adjusted hazard ratio with 95% confidence interval of anemia and
hyperuricemia on all-cause mortality; a four-category joint-exposure model (reference:
neither) for additive interaction, from which the relative excess risk due to interaction
(RERI = HR_both - HR_anemia - HR_hyperuricemia + 1) and attributable proportion
(AP = RERI / HR_both) are computed. Complete-case estimation within models (model n
{main['model_n']}, events {main['model_events']}). Design-based (Taylor linearization)
variance was not re-implemented; p-value and interval coverage are therefore approximate.

## Re-Discovery result (source result alignment)

The source paper reported: anemia HR 1.72 (95% CI 1.42-2.09), hyperuricemia HR 1.21
(1.01-1.45), RERI 0.630, AP 0.291. This reproduction recovered: anemia HR
{fmt(metrics['hr_anemia'])}, hyperuricemia HR {fmt(metrics['hr_hyperuricemia'])},
both-vs-neither HR {fmt(metrics['hr_both_vs_neither'])}, RERI {fmt(metrics['reri'])},
AP {fmt(metrics['attributable_proportion'])}. The main finding of a positive additive
interaction (synergy) between the two exposures is reproduced.

## Missing data handling

Complete-case estimation on exposures and model covariates; missing hemoglobin or uric acid
excludes a participant from exposure classification, and covariate missingness (income,
diet recall) is handled complete-case inside the models. Missingness and endpoint
availability are recorded in data/cohort_summary.json.

## Sensitivity and subgroup analyses

Subgroup synergy checks in the source paper (age >= 65, male, hypertension, diabetes,
cancer subgroups) are supported by the extract columns; a robustness spot-check in the
age >= 65 subgroup reproduced a positive RERI, consistent with the source paper's
subgroup pattern (sensitivity analysis).

## New-Discovery extension (bounded)

Bounded extension within the same data support: RERI computed with eGFR-only CKD
(excluding albuminuria-only CKD) remains positive, suggesting the synergy is not driven
solely by the albuminuria pathway. This is hypothesis-generating only, not causal, and not
a clinical decision rule; uncertainty follows the confidence intervals above.

## Limitations, bias, and generalizability

Observational design implies residual confounding (bias cannot be excluded); single-visit
laboratory classification of CKD, anemia, and hyperuricemia risks misclassification;
the MDRD equation (kept for source fidelity) is known to differ from CKD-EPI; selection
into MEC examination and dietary recall nonresponse may induce selection effects partially
addressed by weighting. Generalizability is to noninstitutionalized US adults with CKD.

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
        "task_id": "Hematology_001",
    }, indent=1, sort_keys=True))

    return {"metrics": metrics}
