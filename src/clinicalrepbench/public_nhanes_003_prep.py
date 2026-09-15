"""Endocrinology_003 extract builder.

Reproduces the cohort of PMID 37755728 (JAMA Cardiol 2023): Prevalence and
Overlap of Cardiac, Renal, and Metabolic (CRM) Conditions in US Adults.

Primary period: NHANES 2015-2016 + 2017-March 2020 prepandemic (combined with
official NCHS weight scaling 2/5.2 and 3.2/5.2). Trend period: NHANES
1999-2000 + 2001-2002 (WTMEC4YR). Cohort: MEC-examined, nonpregnant adults
aged >= 20 years.

Condition definitions:
- CVD: self-reported congestive heart failure, coronary heart disease,
  angina, myocardial infarction, or stroke (MCQ160B-F).
- CKD: eGFR < 60 mL/min/1.73m^2 (CKD-EPI 2021 race-free creatinine equation)
  or urinary albumin-to-creatinine ratio >= 30 mg/g.
- T2D: self-reported diabetes diagnosis (DIQ010 == 1) or HbA1c >= 6.5%.

For 1999-2000 serum creatinine, the NCHS-recommended recalibration
(1.013 x Scr + 0.147) is applied before eGFR computation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

CYCLES = {
    "1999-2000": {
        "period": "1999_2002",
        "files": {"demo": "DEMO.xpt", "mcq": "MCQ.xpt", "diq": "DIQ.xpt",
                  "ghb": "LAB10.xpt", "bio": "LAB18.xpt", "alb": "LAB16.xpt"},
        "weight_col": "WTMEC4YR", "weight_factor": 1.0, "scr_recalibrate": True,
    },
    "2001-2002": {
        "period": "1999_2002",
        "files": {"demo": "DEMO_B.xpt", "mcq": "MCQ_B.xpt", "diq": "DIQ_B.xpt",
                  "ghb": "L10_B.xpt", "bio": "L40_B.xpt", "alb": "L16_B.xpt"},
        "weight_col": "WTMEC4YR", "weight_factor": 1.0, "scr_recalibrate": False,
    },
    "2015-2016": {
        "period": "2015_2020",
        "files": {"demo": "DEMO_I.xpt", "mcq": "MCQ_I.xpt", "diq": "DIQ_I.xpt",
                  "ghb": "GHB_I.xpt", "bio": "BIOPRO_I.xpt", "alb": "ALB_CR_I.xpt"},
        "weight_col": "WTMEC2YR", "weight_factor": 2.0 / 5.2, "scr_recalibrate": False,
    },
    "2017-2020": {
        "period": "2015_2020",
        "files": {"demo": "P_DEMO.xpt", "mcq": "P_MCQ.xpt", "diq": "P_DIQ.xpt",
                  "ghb": "P_GHB.xpt", "bio": "P_BIOPRO.xpt", "alb": "P_ALB_CR.xpt"},
        "weight_col": "WTMECPRP", "weight_factor": 3.2 / 5.2, "scr_recalibrate": False,
    },
}

MCQ_CVD_COLS = ["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"]


def _read_xpt(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    frame = pd.read_sas(path, format="xport")
    frame.columns = [str(c).upper() for c in frame.columns]
    if columns:
        keep = ["SEQN"] + [c for c in columns if c in frame.columns]
        frame = frame[[c for c in keep if c in frame.columns]]
    return frame


def egfr_ckd_epi_2021(scr_mg_dl: pd.Series, age: pd.Series, female: pd.Series) -> pd.Series:
    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    ratio = scr_mg_dl / kappa
    egfr = (142.0
            * np.minimum(ratio, 1.0) ** alpha
            * np.maximum(ratio, 1.0) ** -1.200
            * 0.9938 ** age
            * np.where(female, 1.012, 1.0))
    return pd.Series(egfr, index=scr_mg_dl.index)


def _build_cycle(input_dir: Path, cycle: str, spec: dict) -> pd.DataFrame:
    f = spec["files"]
    demo = _read_xpt(input_dir / f["demo"],
                     ["RIDAGEYR", "RIAGENDR", "RIDRETH1", "RIDEXPRG", "INDFMPIR",
                      spec["weight_col"], "SDMVPSU", "SDMVSTRA"])
    mcq = _read_xpt(input_dir / f["mcq"], MCQ_CVD_COLS)
    diq = _read_xpt(input_dir / f["diq"], ["DIQ010"])
    ghb = _read_xpt(input_dir / f["ghb"], ["LBXGH"])
    bio = _read_xpt(input_dir / f["bio"], ["LBXSCR", "LBDSCR"])
    if "LBXSCR" not in bio.columns and "LBDSCR" in bio.columns:
        bio = bio.rename(columns={"LBDSCR": "LBXSCR"})
    alb = _read_xpt(input_dir / f["alb"], ["URXUMA", "URXUCR"])

    merged = demo
    for part in (mcq, diq, ghb, bio, alb):
        merged = merged.merge(part, on="SEQN", how="left")

    merged["cycle"] = cycle
    merged["period"] = spec["period"]
    merged["mec_weight"] = merged[spec["weight_col"]] * spec["weight_factor"]

    if spec["scr_recalibrate"] and "LBXSCR" in merged:
        merged["LBXSCR"] = 1.013 * merged["LBXSCR"] + 0.147

    return merged


def prepare_public_nhanes_003_extract(
    input_dir: str | Path,
    output_csv: str | Path,
    output_summary_json: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict]:
    input_dir = Path(input_dir)
    frames = [_build_cycle(input_dir, cycle, spec) for cycle, spec in CYCLES.items()]
    raw = pd.concat(frames, ignore_index=True)

    n_input = int(len(raw))
    adults = raw[raw["RIDAGEYR"] >= 20].copy()
    n_under20 = n_input - int(len(adults))
    pregnant = adults["RIDEXPRG"] == 1
    n_pregnant = int(pregnant.sum())
    adults = adults[~pregnant]
    no_weight = adults["mec_weight"].isna() | (adults["mec_weight"] <= 0)
    n_no_mec = int(no_weight.sum())
    adults = adults[~no_weight].copy()

    # Complete-case requirement on the lab components needed to classify all
    # three CRM conditions (serum creatinine, urinary albumin/creatinine, HbA1c),
    # matching the source-paper analytic sample of 11,607.
    missing_labs = (adults["LBXSCR"].isna() | adults["URXUMA"].isna()
                    | adults["URXUCR"].isna() | adults["LBXGH"].isna())
    n_missing_labs = int(missing_labs.sum())
    adults = adults[~missing_labs].copy()

    female = adults["RIAGENDR"] == 2
    adults["female_flag"] = female.astype(int)
    adults["cvd_flag"] = (adults[MCQ_CVD_COLS] == 1).any(axis=1).astype(int)
    adults["t2d_flag"] = ((adults["DIQ010"] == 1) | (adults["LBXGH"] >= 6.5)).astype(int)
    adults["egfr"] = egfr_ckd_epi_2021(adults["LBXSCR"], adults["RIDAGEYR"], female)
    adults["uacr_mg_g"] = adults["URXUMA"] * 100.0 / adults["URXUCR"]
    adults["ckd_flag"] = ((adults["egfr"] < 60) | (adults["uacr_mg_g"] >= 30)).astype(int)
    adults["crm_count"] = adults[["cvd_flag", "ckd_flag", "t2d_flag"]].sum(axis=1)
    adults["age_65plus"] = (adults["RIDAGEYR"] >= 65).astype(int)
    adults["poverty_below_1"] = (adults["INDFMPIR"] < 1.0).astype("Int64")

    out_cols = ["SEQN", "cycle", "period", "RIDAGEYR", "RIAGENDR", "female_flag",
                "RIDRETH1", "INDFMPIR", "poverty_below_1", "mec_weight",
                "SDMVPSU", "SDMVSTRA", "cvd_flag", "ckd_flag", "t2d_flag",
                "crm_count", "age_65plus", "egfr", "uacr_mg_g", "LBXGH",
                "LBXSCR", "DIQ010"]
    analytic = adults[[c for c in out_cols if c in adults.columns]].copy()
    analytic.columns = [c.lower() for c in analytic.columns]

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    analytic.to_csv(output_csv, index=False)

    primary = analytic[analytic["period"] == "2015_2020"]
    summary = {
        "analysis": "nhanes_crm_overlap",
        "source_paper_pmid": "37755728",
        "cycles": list(CYCLES),
        "n_input_rows": n_input,
        "n_excluded_under_20": n_under20,
        "n_excluded_pregnant": n_pregnant,
        "n_excluded_no_mec_weight": n_no_mec,
        "n_excluded_missing_classification_labs": n_missing_labs,
        "n_analytic_all_periods": int(len(analytic)),
        "n_analytic_2015_2020": int(len(primary)),
        "n_analytic_1999_2002": int(len(analytic)) - int(len(primary)),
        "missing_scr_pct_2015_2020": round(float(primary["lbxscr"].isna().mean() * 100), 2),
        "missing_uacr_pct_2015_2020": round(float(primary["uacr_mg_g"].isna().mean() * 100), 2),
        "missing_hba1c_pct_2015_2020": round(float(primary["lbxgh"].isna().mean() * 100), 2),
        "input_dir": str(input_dir),
        "manifest_path": str(manifest_path) if manifest_path else None,
    }
    if output_summary_json:
        Path(output_summary_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_summary_json).write_text(json.dumps(summary, indent=2, sort_keys=True))
    return analytic, summary
