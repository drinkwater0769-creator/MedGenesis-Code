"""Cardiology_003 extract builder.

Reproduces the cohort of PMID 37254774 (Hypertension 2023): sex-specific
associations between blood pressure and CVD mortality, NHANES 1999-2018
(10 cycles) linked to the 2019 public-use NDI mortality file.

Cohort: adults >= 18 years with averaged BP measurements and mortality
linkage eligibility (N = 53,289 in the source paper; 25,899 men and 27,390
women). BP is the mean of up to three readings; 2017-2018 oscillometric
readings are calibrated to the mercury standard (SBP +1.1 men / +2.1 women;
DBP +0.9 men / +0.2 women). CVD mortality = diseases of heart (UCOD 001) or
cerebrovascular disease (UCOD 005) through 2019-12-31.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from clinicalrepbench.nhanes_mortality import stage_lmf, UCOD_HEART, UCOD_CEREBROVASCULAR

SFX = {"1999-2000": "", "2001-2002": "_B", "2003-2004": "_C", "2005-2006": "_D",
       "2007-2008": "_E", "2009-2010": "_F", "2011-2012": "_G", "2013-2014": "_H",
       "2015-2016": "_I", "2017-2018": "_J"}

TC_FILE = {"1999-2000": "LAB13.xpt", "2001-2002": "L13_B.xpt", "2003-2004": "L13_C.xpt"}
BIO_FILE = {"1999-2000": "LAB18.xpt", "2001-2002": "L40_B.xpt", "2003-2004": "L40_C.xpt"}
GLU_FILE = {"1999-2000": "LAB10AM.xpt", "2001-2002": "L10AM_B.xpt", "2003-2004": "L10AM_C.xpt"}


def cycle_files(cycle: str) -> dict:
    s = SFX[cycle]
    return {
        "demo": f"DEMO{s}.xpt", "bpx": f"BPX{s}.xpt", "bpq": f"BPQ{s}.xpt",
        "smq": f"SMQ{s}.xpt", "paq": f"PAQ{s}.xpt", "bmx": f"BMX{s}.xpt",
        "diq": f"DIQ{s}.xpt", "mcq": f"MCQ{s}.xpt",
        "tchol": TC_FILE.get(cycle, f"TCHOL{s}.xpt"),
        "biopro": BIO_FILE.get(cycle, f"BIOPRO{s}.xpt"),
        "glu": GLU_FILE.get(cycle, f"GLU{s}.xpt"),
    }


def _read(input_dir: Path, name: str, cols: list[str]) -> pd.DataFrame:
    frame = pd.read_sas(input_dir / name, format="xport")
    frame.columns = [str(c).upper() for c in frame.columns]
    keep = ["SEQN"] + [c for c in cols if c in frame.columns]
    return frame[keep]


def egfr_ckd_epi_2021(scr: pd.Series, age: pd.Series, female: pd.Series) -> pd.Series:
    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    ratio = scr / kappa
    return pd.Series(142.0 * np.minimum(ratio, 1.0) ** alpha
                     * np.maximum(ratio, 1.0) ** -1.200
                     * 0.9938 ** age * np.where(female, 1.012, 1.0),
                     index=scr.index)


def _build_cycle(input_dir: Path, cycle: str) -> pd.DataFrame:
    f = cycle_files(cycle)
    demo = _read(input_dir, f["demo"],
                 ["RIDAGEYR", "RIAGENDR", "RIDRETH1", "DMDEDUC2", "INDHHIN2", "INDHHINC",
                  "WTMEC2YR", "WTMEC4YR", "SDMVPSU", "SDMVSTRA"])
    bpx = _read(input_dir, f["bpx"], ["BPXSY1", "BPXSY2", "BPXSY3", "BPXSY4",
                                       "BPXDI1", "BPXDI2", "BPXDI3", "BPXDI4"])
    bpq = _read(input_dir, f["bpq"], ["BPQ040A", "BPQ050A"])
    smq = _read(input_dir, f["smq"], ["SMQ020", "SMQ040"])
    paq = _read(input_dir, f["paq"], ["PAD200", "PAD320", "PAQ605", "PAQ650", "PAQ620", "PAQ665"])
    bmx = _read(input_dir, f["bmx"], ["BMXBMI"])
    diq = _read(input_dir, f["diq"], ["DIQ010", "DIQ050", "DIQ070"])
    mcq = _read(input_dir, f["mcq"], ["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"])
    tc = _read(input_dir, f["tchol"], ["LBXTC"])
    bio = _read(input_dir, f["biopro"], ["LBXSCR", "LBDSCR"])
    if "LBXSCR" not in bio.columns and "LBDSCR" in bio.columns:
        bio = bio.rename(columns={"LBDSCR": "LBXSCR"})
    glu = _read(input_dir, f["glu"], ["LBXGLU"])

    merged = demo
    for part in (bpx, bpq, smq, paq, bmx, diq, mcq, tc, bio, glu):
        merged = merged.merge(part, on="SEQN", how="left")
    merged["cycle"] = cycle

    # Serum creatinine calibration for applicable years
    if cycle == "1999-2000":
        merged["LBXSCR"] = 1.013 * merged["LBXSCR"] + 0.147
    elif cycle == "2005-2006":
        merged["LBXSCR"] = -0.016 + 0.978 * merged["LBXSCR"]

    # 10-cycle combined MEC weight (NCHS rule: 4/20 x WTMEC4YR for 1999-2002,
    # 2/20 x WTMEC2YR otherwise)
    if cycle in ("1999-2000", "2001-2002"):
        merged["mec_weight10"] = merged["WTMEC4YR"] * (4.0 / 20.0)
    else:
        merged["mec_weight10"] = merged["WTMEC2YR"] * (2.0 / 20.0)
    return merged


def prepare_public_nhanes_cardio003_extract(
    input_dir: str | Path,
    output_csv: str | Path,
    output_summary_json: str | Path | None = None,
    manifest_path: str | Path | None = None,
    lmf_cache_dir: str | Path | None = None,
    download_lmf: bool = True,
) -> tuple[pd.DataFrame, dict]:
    input_dir = Path(input_dir)
    cycles = list(SFX)
    raw = pd.concat([_build_cycle(input_dir, c) for c in cycles], ignore_index=True)
    n_input = int(len(raw))

    lmf = stage_lmf(cycles, lmf_cache_dir or (input_dir / "lmf"), download=download_lmf)
    raw = raw.merge(lmf.drop(columns=["cycle"]), on="SEQN", how="left")

    adults = raw[raw["RIDAGEYR"] >= 18].copy()
    n_under18 = n_input - int(len(adults))

    sy = adults[["BPXSY1", "BPXSY2", "BPXSY3", "BPXSY4"]]
    di = adults[["BPXDI1", "BPXDI2", "BPXDI3", "BPXDI4"]]
    adults["sbp"] = sy.mean(axis=1)
    adults["dbp"] = di.where(di > 0).mean(axis=1)  # zero DBP readings are artifacts

    female = adults["RIAGENDR"] == 2
    is_j = adults["cycle"] == "2017-2018"
    adults.loc[is_j & ~female, "sbp"] += 1.1
    adults.loc[is_j & female, "sbp"] += 2.1
    adults.loc[is_j & ~female, "dbp"] += 0.9
    adults.loc[is_j & female, "dbp"] += 0.2

    no_bp = adults["sbp"].isna() | adults["dbp"].isna()
    n_no_bp = int(no_bp.sum())
    adults = adults[~no_bp]
    not_eligible = ~(adults["eligstat"] == 1) | adults["mortstat"].isna() | adults["permth_exm"].isna()
    n_not_linked = int(not_eligible.sum())
    adults = adults[~not_eligible].copy()

    female = adults["RIAGENDR"] == 2
    adults["female_flag"] = female.astype(int)
    adults["followup_years"] = adults["permth_exm"] / 12.0
    adults["death_allcause"] = (adults["mortstat"] == 1).astype(int)
    adults["death_heart"] = ((adults["mortstat"] == 1) & (adults["ucod_leading"] == UCOD_HEART)).astype(int)
    adults["death_cerebro"] = ((adults["mortstat"] == 1) & (adults["ucod_leading"] == UCOD_CEREBROVASCULAR)).astype(int)
    adults["death_cvd"] = ((adults["death_heart"] == 1) | (adults["death_cerebro"] == 1)).astype(int)

    adults["sbp_cat"] = pd.cut(adults["sbp"], [-np.inf, 100, 110, 120, 130, 140, 160, np.inf],
                               right=False, labels=["lt100", "100_109", "110_119", "120_129",
                                                    "130_139", "140_159", "ge160"]).astype(str)
    adults["dbp_cat"] = pd.cut(adults["dbp"], [-np.inf, 50, 60, 70, 80, 90, 100, np.inf],
                               right=False, labels=["lt50", "50_59", "60_69", "70_79",
                                                    "80_89", "90_99", "ge100"]).astype(str)

    adults["egfr"] = egfr_ckd_epi_2021(adults["LBXSCR"], adults["RIDAGEYR"], female)
    adults["egfr_lt60"] = (adults["egfr"] < 60).astype(int)
    adults["diabetes"] = ((adults["DIQ010"] == 1) | (adults["DIQ050"] == 1)
                          | (adults["DIQ070"] == 1) | (adults["LBXGLU"] >= 126)).astype(int)
    adults["prior_cvd"] = (adults[["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"]] == 1).any(axis=1).astype(int)
    adults["antihtn_med"] = (adults["BPQ050A"] == 1).astype(int)
    adults["smoking"] = np.select(
        [adults["SMQ020"] == 2, (adults["SMQ020"] == 1) & (adults["SMQ040"] == 3),
         (adults["SMQ020"] == 1) & (adults["SMQ040"].isin([1, 2]))],
        ["never", "former", "current"], default="missing")
    vig = (adults["PAD200"] == 1) | (adults["PAQ605"] == 1) | (adults["PAQ650"] == 1)
    mod = (adults["PAD320"] == 1) | (adults["PAQ620"] == 1) | (adults["PAQ665"] == 1)
    adults["phys_activity"] = np.select([vig, mod], ["high", "moderate"], default="none")
    adults["educ_lt_hs"] = (adults["DMDEDUC2"].isin([1, 2])).astype(int)
    income = adults["INDHHIN2"].fillna(adults.get("INDHHINC"))
    adults["income_lt_55k"] = np.select(
        [income.isin([1, 2, 3, 4, 5, 6, 7, 8, 13]), income.isin([9, 10, 11, 14, 15])],
        [1, 0], default=np.nan)
    adults["race_eth"] = adults["RIDRETH1"].map(
        {1: "mexican_american", 2: "other_hispanic", 3: "nh_white", 4: "nh_black", 5: "other"})

    out_cols = ["SEQN", "cycle", "RIDAGEYR", "female_flag", "race_eth", "educ_lt_hs",
                "income_lt_55k", "smoking", "phys_activity", "BMXBMI", "diabetes", "LBXTC",
                "egfr", "egfr_lt60", "antihtn_med", "prior_cvd", "sbp", "dbp", "sbp_cat",
                "dbp_cat", "mec_weight10", "SDMVPSU", "SDMVSTRA", "followup_years",
                "death_allcause", "death_cvd", "death_heart", "death_cerebro"]
    analytic = adults[[c for c in out_cols if c in adults.columns]].copy()
    analytic.columns = [c.lower() for c in analytic.columns]

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    analytic.to_csv(output_csv, index=False)

    summary = {
        "analysis": "nhanes_bp_cvd_mortality_sex",
        "source_paper_pmid": "37254774",
        "cycles": cycles,
        "n_input_rows": n_input,
        "n_excluded_under_18": n_under18,
        "n_excluded_no_bp": n_no_bp,
        "n_excluded_not_mortality_linked": n_not_linked,
        "n_analytic": int(len(analytic)),
        "n_men": int((analytic["female_flag"] == 0).sum()),
        "n_women": int((analytic["female_flag"] == 1).sum()),
        "n_deaths_allcause": int(analytic["death_allcause"].sum()),
        "n_deaths_cvd": int(analytic["death_cvd"].sum()),
        "median_followup_years": round(float(analytic["followup_years"].median()), 3),
        "input_dir": str(input_dir),
        "manifest_path": str(manifest_path) if manifest_path else None,
    }
    if output_summary_json:
        Path(output_summary_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_summary_json).write_text(json.dumps(summary, indent=2, sort_keys=True))
    return analytic, summary
