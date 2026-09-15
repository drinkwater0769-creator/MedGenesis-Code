"""Hematology_001 extract builder.

Reproduces the cohort of PMID 38586465 (Renal Failure 2024): interaction
between anemia and hyperuricemia in all-cause mortality among US adults with
CKD, NHANES 2009-2018 linked to the 2019 public-use NDI mortality file.

Cohort: adults >= 18 years with CKD (UACR > 30 mg/g and/or eGFR < 60 by the
MDRD equation 175 x Scr^-1.154 x age^-0.203 x 1.212[if Black] x 0.742[if
female]), excluding implausible total energy intake (< 500 or > 8,000 kcal in
men; < 500 or > 5,000 kcal in women) and participants without mortality
linkage. Anemia: hemoglobin < 13 g/dL (men) / < 12 g/dL (women). Hyperuricemia:
serum uric acid > 7 mg/dL (men) / > 6 mg/dL (women).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from clinicalrepbench.nhanes_mortality import stage_lmf

SFX = {"2009-2010": "_F", "2011-2012": "_G", "2013-2014": "_H",
       "2015-2016": "_I", "2017-2018": "_J"}


def cycle_files(cycle: str) -> dict:
    s = SFX[cycle]
    return {"demo": f"DEMO{s}.xpt", "cbc": f"CBC{s}.xpt", "biopro": f"BIOPRO{s}.xpt",
            "alb": f"ALB_CR{s}.xpt", "bpq": f"BPQ{s}.xpt", "bpx": f"BPX{s}.xpt",
            "diq": f"DIQ{s}.xpt", "mcq": f"MCQ{s}.xpt", "smq": f"SMQ{s}.xpt",
            "paq": f"PAQ{s}.xpt", "diet": f"DR1TOT{s}.xpt", "ghb": f"GHB{s}.xpt",
            "glu": f"GLU{s}.xpt"}


def _read(input_dir: Path, name: str, cols: list[str]) -> pd.DataFrame:
    frame = pd.read_sas(input_dir / name, format="xport")
    frame.columns = [str(c).upper() for c in frame.columns]
    keep = ["SEQN"] + [c for c in cols if c in frame.columns]
    return frame[keep]


def egfr_mdrd(scr: pd.Series, age: pd.Series, black: pd.Series, female: pd.Series) -> pd.Series:
    return pd.Series(175.0 * scr ** -1.154 * age ** -0.203
                     * np.where(black, 1.212, 1.0) * np.where(female, 0.742, 1.0),
                     index=scr.index)


def _build_cycle(input_dir: Path, cycle: str) -> pd.DataFrame:
    f = cycle_files(cycle)
    demo = _read(input_dir, f["demo"], ["RIDAGEYR", "RIAGENDR", "RIDRETH1", "DMDMARTL",
                                        "INDFMPIR", "WTMEC2YR", "SDMVPSU", "SDMVSTRA"])
    parts = [
        _read(input_dir, f["cbc"], ["LBXHGB"]),
        _read(input_dir, f["biopro"], ["LBXSCR", "LBXSUA"]),
        _read(input_dir, f["alb"], ["URXUMA", "URXUCR"]),
        _read(input_dir, f["bpq"], ["BPQ020", "BPQ050A"]),
        _read(input_dir, f["bpx"], ["BPXSY1", "BPXSY2", "BPXSY3", "BPXDI1", "BPXDI2", "BPXDI3"]),
        _read(input_dir, f["diq"], ["DIQ010", "DIQ050", "DIQ070"]),
        _read(input_dir, f["mcq"], ["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F", "MCQ220"]),
        _read(input_dir, f["smq"], ["SMQ020", "SMQ040"]),
        _read(input_dir, f["paq"], ["PAQ605", "PAD615", "PAQ620", "PAD630", "PAQ635", "PAD645",
                                     "PAQ650", "PAD660", "PAQ665", "PAD675"]),
        _read(input_dir, f["diet"], ["DR1TKCAL", "DR1TCARB"]),
        _read(input_dir, f["ghb"], ["LBXGH"]),
        _read(input_dir, f["glu"], ["LBXGLU"]),
    ]
    merged = demo
    for p in parts:
        merged = merged.merge(p, on="SEQN", how="left")
    merged["cycle"] = cycle
    merged["mec_weight5"] = merged["WTMEC2YR"] / 5.0
    return merged


def _met_minutes(d: pd.DataFrame) -> pd.Series:
    """Weekly MET-minutes from the PAQ recall items (standard NHANES MET values:
    vigorous 8.0, moderate 4.0, walk/bicycle 4.0)."""
    def contrib(flag, minutes, met):
        m = d[minutes].where(d[flag] == 1, 0.0).fillna(0.0)
        return m.clip(lower=0, upper=1200) * met
    total = (contrib("PAQ605", "PAD615", 8.0) + contrib("PAQ620", "PAD630", 4.0)
             + contrib("PAQ635", "PAD645", 4.0) + contrib("PAQ650", "PAD660", 8.0)
             + contrib("PAQ665", "PAD675", 4.0))
    return total


def prepare_public_nhanes_hema001_extract(
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

    female = adults["RIAGENDR"] == 2
    black = adults["RIDRETH1"] == 4
    adults["egfr"] = egfr_mdrd(adults["LBXSCR"], adults["RIDAGEYR"], black, female)
    adults["uacr_mg_g"] = adults["URXUMA"] * 100.0 / adults["URXUCR"]
    ckd = (adults["egfr"] < 60) | (adults["uacr_mg_g"] > 30)
    n_not_ckd = int((~ckd.fillna(False)).sum())
    adults = adults[ckd.fillna(False)].copy()

    # Source-paper exclusions: missing hemoglobin or uric acid, then dietary
    # recall required with plausible total energy intake.
    miss_lab = adults["LBXHGB"].isna() | adults["LBXSUA"].isna()
    n_miss_lab = int(miss_lab.sum())
    adults = adults[~miss_lab].copy()
    female = adults["RIAGENDR"] == 2
    kcal = adults["DR1TKCAL"]
    ok_energy = kcal.notna() & (kcal >= 500) & np.where(female, kcal <= 5000, kcal <= 8000)
    n_bad_energy = int((~ok_energy).sum())
    adults = adults[ok_energy].copy()

    not_linked = ~(adults["eligstat"] == 1) | adults["mortstat"].isna() | adults["permth_exm"].isna()
    n_not_linked = int(not_linked.sum())
    adults = adults[~not_linked].copy()

    female = adults["RIAGENDR"] == 2
    adults["female_flag"] = female.astype(int)
    adults["anemia"] = np.where(female, adults["LBXHGB"] < 12.0, adults["LBXHGB"] < 13.0).astype(float)
    adults.loc[adults["LBXHGB"].isna(), "anemia"] = np.nan
    adults["hyperuricemia"] = np.where(female, adults["LBXSUA"] > 6.0, adults["LBXSUA"] > 7.0).astype(float)
    adults.loc[adults["LBXSUA"].isna(), "hyperuricemia"] = np.nan
    adults["followup_years"] = adults["permth_exm"] / 12.0
    adults["death_allcause"] = (adults["mortstat"] == 1).astype(int)

    sbp = adults[["BPXSY1", "BPXSY2", "BPXSY3"]].mean(axis=1)
    dbp = adults[["BPXDI1", "BPXDI2", "BPXDI3"]].where(adults[["BPXDI1", "BPXDI2", "BPXDI3"]] > 0).mean(axis=1)
    adults["hypertension"] = ((adults["BPQ020"] == 1) | (adults["BPQ050A"] == 1)
                              | (sbp >= 140) | (dbp >= 90)).astype(int)
    adults["diabetes"] = ((adults["DIQ010"] == 1) | (adults["DIQ050"] == 1) | (adults["DIQ070"] == 1)
                          | (adults["LBXGH"] >= 6.5) | (adults["LBXGLU"] >= 126)).astype(int)
    adults["cvd"] = (adults[["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"]] == 1).any(axis=1).astype(int)
    adults["cancer"] = (adults["MCQ220"] == 1).astype(int)
    adults["smoking"] = np.select(
        [adults["SMQ020"] == 2, (adults["SMQ020"] == 1) & (adults["SMQ040"] == 3),
         (adults["SMQ020"] == 1) & (adults["SMQ040"].isin([1, 2]))],
        ["never", "former", "current"], default="missing")
    adults["met_min_week"] = _met_minutes(adults)
    adults["married_partner"] = (adults["DMDMARTL"].isin([1, 6])).astype(int)
    adults["carb_supply_ratio"] = adults["DR1TCARB"] * 4.0 / adults["DR1TKCAL"] * 100.0
    adults["race_eth"] = adults["RIDRETH1"].map(
        {1: "mexican_american", 2: "other_hispanic", 3: "nh_white", 4: "nh_black", 5: "other"})

    out_cols = ["SEQN", "cycle", "RIDAGEYR", "female_flag", "race_eth", "married_partner",
                "INDFMPIR", "smoking", "met_min_week", "hypertension", "cvd", "diabetes",
                "cancer", "carb_supply_ratio", "LBXHGB", "LBXSUA", "egfr", "uacr_mg_g",
                "anemia", "hyperuricemia", "mec_weight5", "SDMVPSU", "SDMVSTRA",
                "followup_years", "death_allcause"]
    analytic = adults[[c for c in out_cols if c in adults.columns]].copy()
    analytic.columns = [c.lower() for c in analytic.columns]

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    analytic.to_csv(output_csv, index=False)

    summary = {
        "analysis": "nhanes_ckd_anemia_hyperuricemia_mortality",
        "source_paper_pmid": "38586465",
        "cycles": cycles,
        "n_input_rows": n_input,
        "n_excluded_under_18": n_under18,
        "n_excluded_not_ckd_or_unclassifiable": n_not_ckd,
        "n_excluded_missing_hb_or_ua": n_miss_lab,
        "n_excluded_missing_or_implausible_energy": n_bad_energy,
        "n_excluded_not_mortality_linked": n_not_linked,
        "n_analytic": int(len(analytic)),
        "n_deaths_allcause": int(analytic["death_allcause"].sum()),
        "input_dir": str(input_dir),
        "manifest_path": str(manifest_path) if manifest_path else None,
    }
    if output_summary_json:
        Path(output_summary_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_summary_json).write_text(json.dumps(summary, indent=2, sort_keys=True))
    return analytic, summary
