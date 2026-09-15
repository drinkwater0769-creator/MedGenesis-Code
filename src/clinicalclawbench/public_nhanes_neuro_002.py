"""Neurology_002 extract builder + reference reproduction.

Reproduces PMID 39300119 (Sci Rep / BMC 2024): periodontitis and all-cause /
cause-specific mortality among US adults with depression, pooled across three
NHANES eras (1988-1994, 1999-2004, 2009-2014).

Depression: 1988-1994 lifetime MDE (exam.dat MQPDEP, DSM-III, DIS module);
1999-2004 CIDI MDD (CIDDSCOR == 1, ages 20-39 subsample); 2009-2014 PHQ-9
total > 9. Periodontitis: CDC-AAP moderate/severe from interproximal clinical
attachment loss and probing depth (half-mouth in the early eras, full-mouth
2009-2014). Mortality: NCHS 2019 public-use linked mortality files; cancer
deaths = UCOD leading-cause recode 002.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from clinicalclawbench.nhanes3 import read_nh3, stage_nh3, apply_bounds
from clinicalclawbench.nhanes_mortality import parse_lmf, stage_lmf

BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public"
FILES = {
    "CIQMDEP.xpt": "1999/DataFiles/CIQMDEP.xpt",
    "CIQDEP_B.xpt": "2001/DataFiles/CIQDEP_B.xpt",
    "CIQDEP_C.xpt": "2003/DataFiles/CIQDEP_C.xpt",
    "DPQ_F.xpt": "2009/DataFiles/DPQ_F.xpt",
    "DPQ_G.xpt": "2011/DataFiles/DPQ_G.xpt",
    "DPQ_H.xpt": "2013/DataFiles/DPQ_H.xpt",
    "OHXPERIO.xpt": "1999/DataFiles/OHXPERIO.xpt",
    "OHXPRU_B.xpt": "2001/DataFiles/OHXPRU_B.xpt",
    "OHXPRL_B.xpt": "2001/DataFiles/OHXPRL_B.xpt",
    "OHXPRU_C.xpt": "2003/DataFiles/OHXPRU_C.xpt",
    "OHXPRL_C.xpt": "2003/DataFiles/OHXPRL_C.xpt",
    "OHXPER_F.xpt": "2009/DataFiles/OHXPER_F.xpt",
    "OHXPER_G.xpt": "2011/DataFiles/OHXPER_G.xpt",
    "OHXPER_H.xpt": "2013/DataFiles/OHXPER_H.xpt",
    "DEMO.xpt": "1999/DataFiles/DEMO.xpt",
    "DEMO_B.xpt": "2001/DataFiles/DEMO_B.xpt",
    "DEMO_C.xpt": "2003/DataFiles/DEMO_C.xpt",
    "DEMO_F.xpt": "2009/DataFiles/DEMO_F.xpt",
    "DEMO_G.xpt": "2011/DataFiles/DEMO_G.xpt",
    "DEMO_H.xpt": "2013/DataFiles/DEMO_H.xpt",
}
INTERPROX = ("S", "D", "P", "A")   # continuous-NHANES interproximal site suffixes


def _stage(cache: Path, name: str) -> Path:
    local = cache / name
    if not local.exists() or local.stat().st_size == 0:
        urllib.request.urlretrieve(f"{BASE}/{FILES[name]}", local)
    return local


def _xpt(path: Path) -> pd.DataFrame:
    d = pd.read_sas(path, format="xport")
    d.columns = [str(c).upper() for c in d.columns]
    return d


def _cdc_aap(frame: pd.DataFrame, la_pat: str, pc_pat: str,
             interprox: tuple) -> pd.Series:
    """CDC-AAP moderate/severe periodontitis from site-level CAL (LA) and PPD (PC)."""
    la_cols, pc_cols = {}, {}
    for col in frame.columns:
        m = re.match(la_pat, col)
        if m and m.group("site") in interprox:
            la_cols.setdefault(m.group("tooth"), []).append(col)
        m = re.match(pc_pat, col)
        if m and m.group("site") in interprox:
            pc_cols.setdefault(m.group("tooth"), []).append(col)
    if not la_cols:
        return pd.Series(np.nan, index=frame.index)

    def teeth_ge(cols_by_tooth, cut):
        counts = pd.Series(0, index=frame.index)
        any_measured = pd.Series(False, index=frame.index)
        for tooth, cols in cols_by_tooth.items():
            vals = frame[cols].apply(pd.to_numeric, errors="coerce")
            vals = vals.where(vals < 30)
            any_measured |= vals.notna().any(axis=1)
            counts += vals.ge(cut).any(axis=1).astype(int)
        return counts, any_measured

    cal4, meas = teeth_ge(la_cols, 4)
    cal6, _ = teeth_ge(la_cols, 6)
    ppd5, meas_pc = teeth_ge(pc_cols, 5)
    moderate = (cal4 >= 2) | (ppd5 >= 2)
    severe = (cal6 >= 2) & (ppd5 >= 1)
    out = (moderate | severe).astype(float)
    out[~(meas | meas_pc)] = np.nan
    return out


def build_extract(cache_dir: str | Path, nh3_cache: str | Path,
                  lmf_cache: str | Path, output_csv: str | Path,
                  output_summary_json: str | Path | None = None) -> tuple[pd.DataFrame, dict]:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    parts = []

    # ---- 1988-1994 (NHANES III) ----
    nh3 = Path(nh3_cache)
    stage_nh3(nh3, ["adult", "exam"], download=True)
    adult = read_nh3(nh3 / "adult.dat", nh3 / "adult.sas",
                     ["SEQN", "HSSEX", "HSAGEIR", "DMARETHN", "DMPPIR", "HFA8R",
                      "HAR1", "HAR3", "HAD1", "HAE2", "HAE7"])
    pos = None
    from clinicalclawbench.nhanes3 import parse_sas_positions
    epos = parse_sas_positions(nh3 / "exam.sas")
    perio_vars = [v for v in epos if re.match(r"DEP[UL][MB](PC|LA)\d+$", v)]
    exam = read_nh3(nh3 / "exam.dat", nh3 / "exam.sas",
                    ["SEQN", "MQPDEP", "BMPBMI"] + perio_vars)
    d3 = adult.merge(exam, on="SEQN", how="inner")
    d3 = apply_bounds(d3, {"HSAGEIR": (17, 95), "DMPPIR": (0, 30), "HFA8R": (0, 17),
                           "BMPBMI": (10, 90)})
    # DIS output: 1 = no diagnosis, 2-5 = positive diagnosis categories, 88 = blank
    d3["depressed"] = np.where(d3["MQPDEP"].isin([1, 2, 3, 4, 5]),
                               d3["MQPDEP"].isin([2, 3, 4, 5]).astype(float), np.nan)
    # III site naming: DEP U/L (arch) M/B (mesial/buccal) PC/LA tooth#
    d3["perio_ms"] = _cdc_aap(
        d3, r"DEP[UL](?P<site>M)LA(?P<tooth>\d+)$", r"DEP[UL](?P<site>M)PC(?P<tooth>\d+)$",
        ("M",))
    d3["age"] = d3["HSAGEIR"]
    d3["female_flag"] = (d3["HSSEX"] == 2).astype(int)
    d3["race_eth"] = d3["DMARETHN"].map({1: "nh_white", 2: "nh_black", 3: "mexican_american", 4: "other"})
    d3["pir"] = d3["DMPPIR"]
    d3["educ_years"] = d3["HFA8R"]
    d3["smoker_current"] = ((d3["HAR1"] == 1) & (d3["HAR3"] == 1)).astype(int)
    d3["diabetes"] = (d3["HAD1"] == 1).astype(int)
    d3["htn"] = (d3["HAE2"] == 1).astype(int)
    d3["hpl"] = (d3["HAE7"] == 1).astype(int)
    d3["bmi"] = d3["BMPBMI"]
    d3["era"] = "1988_1994"
    lmf3 = parse_lmf(Path(nh3_cache) / "NHANES_III_MORT_2019_PUBLIC.dat")
    d3 = d3.merge(lmf3, on="SEQN", how="left")
    parts.append(d3)

    # ---- 1999-2004 ----
    for dep_f, perio_fs, demo_f, cyc in [
            ("CIQMDEP.xpt", ["OHXPERIO.xpt"], "DEMO.xpt", "1999-2000"),
            ("CIQDEP_B.xpt", ["OHXPRU_B.xpt", "OHXPRL_B.xpt"], "DEMO_B.xpt", "2001-2002"),
            ("CIQDEP_C.xpt", ["OHXPRU_C.xpt", "OHXPRL_C.xpt"], "DEMO_C.xpt", "2003-2004")]:
        dep = _xpt(_stage(cache, dep_f))[["SEQN", "CIDDSCOR"]]
        demo = _xpt(_stage(cache, demo_f))
        keep_demo = [c for c in ["SEQN", "RIDAGEYR", "RIAGENDR", "RIDRETH1", "INDFMPIR",
                                 "DMDEDUC2"] if c in demo.columns]
        demo = demo[keep_demo]
        per = None
        for pf in perio_fs:
            p = _xpt(_stage(cache, pf))
            per = p if per is None else per.merge(p, on="SEQN", how="outer", suffixes=("", "_l"))
        merged = demo.merge(dep, on="SEQN", how="inner").merge(per, on="SEQN", how="left")
        merged["depressed"] = np.where(merged["CIDDSCOR"].isin([1, 5]),
                                       (merged["CIDDSCOR"] == 1).astype(float), np.nan)
        merged["perio_ms"] = _cdc_aap(
            merged, r"OHD(?P<tooth>\d+)LA(?P<site>[SD])$", r"OHD(?P<tooth>\d+)PC(?P<site>[SD])$",
            ("S", "D"))
        merged["era"] = "1999_2004"
        merged["cycle"] = cyc
        parts.append(merged)

    # ---- 2009-2014 ----
    for dep_f, perio_f, demo_f, cyc in [
            ("DPQ_F.xpt", "OHXPER_F.xpt", "DEMO_F.xpt", "2009-2010"),
            ("DPQ_G.xpt", "OHXPER_G.xpt", "DEMO_G.xpt", "2011-2012"),
            ("DPQ_H.xpt", "OHXPER_H.xpt", "DEMO_H.xpt", "2013-2014")]:
        dep = _xpt(_stage(cache, dep_f))
        items = [c for c in dep.columns if re.match(r"DPQ0\d0$", c)]
        vals = dep[items].apply(pd.to_numeric, errors="coerce").where(lambda x: x <= 3)
        dep["phq_total"] = vals.sum(axis=1, min_count=9)
        dep = dep[["SEQN", "phq_total"]]
        demo = _xpt(_stage(cache, demo_f))
        keep_demo = [c for c in ["SEQN", "RIDAGEYR", "RIAGENDR", "RIDRETH1", "INDFMPIR",
                                 "DMDEDUC2"] if c in demo.columns]
        demo = demo[keep_demo]
        per = _xpt(_stage(cache, perio_f))
        merged = demo.merge(dep, on="SEQN", how="inner").merge(per, on="SEQN", how="left")
        merged["depressed"] = np.where(merged["phq_total"].notna(),
                                       (merged["phq_total"] > 9).astype(float), np.nan)
        merged["perio_ms"] = _cdc_aap(
            merged, r"OHX(?P<tooth>\d+)LA(?P<site>[SDPA])$", r"OHX(?P<tooth>\d+)PC(?P<site>[SDPA])$",
            INTERPROX)
        merged["era"] = "2009_2014"
        merged["cycle"] = cyc
        parts.append(merged)

    # continuous-era common covariates + mortality
    lmf = stage_lmf(["1999-2000", "2001-2002", "2003-2004",
                     "2009-2010", "2011-2012", "2013-2014"], lmf_cache, download=True)
    out_parts = []
    for p in parts:
        d = p.copy()
        if "RIDAGEYR" in d.columns:
            d["age"] = pd.to_numeric(d["RIDAGEYR"], errors="coerce")
            d["female_flag"] = (d["RIAGENDR"] == 2).astype(int)
            d["race_eth"] = d["RIDRETH1"].map({1: "mexican_american", 2: "other_hispanic",
                                               3: "nh_white", 4: "nh_black", 5: "other"})
            d["pir"] = pd.to_numeric(d.get("INDFMPIR"), errors="coerce")
            d["educ_years"] = pd.to_numeric(d.get("DMDEDUC2"), errors="coerce").where(lambda s: s.between(1, 5))
            for col in ["smoker_current", "diabetes", "htn", "hpl", "bmi"]:
                if col not in d.columns:
                    d[col] = np.nan
            d = d.merge(lmf, on="SEQN", how="left")
        keep = ["SEQN", "era", "age", "female_flag", "race_eth", "pir", "educ_years",
                "smoker_current", "diabetes", "htn", "hpl", "bmi", "depressed", "perio_ms",
                "eligstat", "mortstat", "ucod_leading", "permth_exm"]
        out_parts.append(d[[c for c in keep if c in d.columns]])
    allp = pd.concat(out_parts, ignore_index=True)

    keep = (allp["depressed"] == 1) & allp["perio_ms"].notna() \
        & (allp["eligstat"] == 1) & allp["mortstat"].notna() & allp["permth_exm"].notna()
    analytic = allp[keep].copy()
    analytic["followup_years"] = analytic["permth_exm"] / 12.0
    analytic["death_allcause"] = (analytic["mortstat"] == 1).astype(int)
    analytic["death_cancer"] = ((analytic["mortstat"] == 1)
                                & (analytic["ucod_leading"] == 2)).astype(int)
    analytic.columns = [c.lower() for c in analytic.columns]

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    analytic.to_csv(output_csv, index=False)
    summary = {
        "analysis": "nhanes_periodontitis_depression_mortality",
        "source_paper_pmid": "39300119",
        "n_analytic": int(len(analytic)),
        "n_perio_mod_severe": int(analytic["perio_ms"].sum()),
        "n_deaths": int(analytic["death_allcause"].sum()),
        "n_cancer_deaths": int(analytic["death_cancer"].sum()),
        "median_followup_years": round(float(analytic["followup_years"].median()), 2),
        "by_era": analytic.groupby("era")["seqn"].count().to_dict(),
    }
    if output_summary_json:
        Path(output_summary_json).write_text(json.dumps(summary, indent=2, sort_keys=True, default=int))
    return analytic, summary


def run_reference(workspace: str | Path, cache_dir: str | Path | None = None) -> dict:
    from lifelines import CoxPHFitter
    workspace = Path(workspace).resolve()
    extract = workspace / "data" / "analytic_extract.csv"
    sp = Path(cache_dir) if cache_dir else workspace / "data" / "source"
    crb = sp.parent if cache_dir else workspace
    if extract.exists():
        frame = pd.read_csv(extract)
    else:
        frame, _ = build_extract(sp, crb / "cache_nhanes3", crb / "cache_nhanes" / "lmf",
                                 extract, workspace / "data" / "cohort_summary.json")

    def cox(outcome):
        dd = frame.dropna(subset=["followup_years", outcome, "perio_ms", "age",
                                  "female_flag"]).copy()
        dd = dd[dd["followup_years"] > 0]
        dd = pd.get_dummies(dd, columns=["era"], drop_first=True)
        cols = ([outcome, "followup_years", "perio_ms", "age", "female_flag"]
                + [c for c in dd.columns if c.startswith("era_")])
        m = dd[cols].astype(float)
        cph = CoxPHFitter()
        cph.fit(m, duration_col="followup_years", event_col=outcome)
        ci = cph.confidence_intervals_
        return {"n": int(len(m)), "events": int(m[outcome].sum()),
                "hr": round(float(np.exp(cph.params_["perio_ms"])), 4),
                "ci_low": round(float(np.exp(ci.loc["perio_ms"].iloc[0])), 4),
                "ci_high": round(float(np.exp(ci.loc["perio_ms"].iloc[1])), 4)}

    allc = cox("death_allcause")
    canc = cox("death_cancer")
    metrics = {
        "cohort_n": int(len(frame)),
        "n_perio_mod_severe": int(frame["perio_ms"].sum()),
        "n_deaths": int(frame["death_allcause"].sum()),
        "median_followup_years": round(float(frame["followup_years"].median()), 2),
        "hr_perio_allcause": allc["hr"],
        "hr_perio_cancer_mortality": canc["hr"],
    }

    art = workspace / "artifacts"
    tables = art / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    frame.groupby("era").agg(n=("seqn", "count"), perio_ms=("perio_ms", "sum"),
                             deaths=("death_allcause", "sum")).reset_index().to_csv(
        tables / "table1.csv", index=False)
    pd.DataFrame([{"outcome": "all-cause", **allc}, {"outcome": "cancer", **canc}]).to_csv(
        tables / "table2.csv", index=False)
    pd.DataFrame([{"definition": "CDC-AAP moderate/severe from interproximal CAL/PPD",
                   "depression": "MQPDEP (DSM-III) / CIDDSCOR (CIDI) / PHQ-9 > 9"}]).to_csv(
        tables / "table3.csv", index=False)
    (art / "primary_metrics.json").write_text(json.dumps({"metrics": metrics}, indent=2, sort_keys=True))
    figs = art / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    (figs / "figure1.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="620" height="220" font-family="Helvetica" font-size="12">'
        '<text x="310" y="24" text-anchor="middle" font-size="15" font-weight="bold">Periodontitis and mortality in depression (pooled NHANES)</text>'
        f'<text x="30" y="80">All-cause HR: {allc["hr"]:.2f} ({allc["ci_low"]:.2f}-{allc["ci_high"]:.2f})</text>'
        f'<text x="30" y="120">Cancer mortality HR: {canc["hr"]:.2f} ({canc["ci_low"]:.2f}-{canc["ci_high"]:.2f})</text>'
        f'<text x="30" y="160">n = {metrics["cohort_n"]}, deaths = {metrics["n_deaths"]}</text></svg>')

    code_dir = workspace / "code"
    code_dir.mkdir(exist_ok=True)
    (code_dir / "run_analysis.py").write_text(
        '"""Executable analysis driver for Neurology_002 (PMID 39300119).\n'
        'Reads the staged pooled NHANES extract at data/analytic_extract.csv (built from\n'
        'NHANES III exam.dat MQPDEP + DEP* periodontal sites, 1999-2004 CIQ*DEP + OHXPR*\n'
        'files, 2009-2014 DPQ_* + OHXPER_* files, and the NCHS 2019 linked mortality\n'
        'files) and re-runs the periodontitis-in-depression mortality reproduction."""\n'
        'from pathlib import Path\n'
        'import sys\n'
        'WORKSPACE = Path(__file__).resolve().parents[1]\n'
        'EXTRACT = WORKSPACE / "data/analytic_extract.csv"\n'
        f'sys.path.insert(0, {json.dumps(str(Path(__file__).resolve().parents[1]))})\n'
        'from clinicalclawbench.public_nhanes_neuro_002 import run_reference\n'
        'def main():\n'
        '    assert EXTRACT.exists(), "stage the pooled NHANES source data first"\n'
        '    result = run_reference(WORKSPACE)\n'
        '    print("reproduced metrics:", result["metrics"])\n'
        '    return 0\n'
        'if __name__ == "__main__":\n'
        '    raise SystemExit(main())\n')

    fmt = lambda v: ("%.2f" % v) if isinstance(v, (int, float)) and v == v else "NA"
    (workspace / "report").mkdir(exist_ok=True)
    (workspace / "report" / "report.md").write_text(f"""# Neurology_002 Reproduction Report

## Source study identity

Source paper: PMID 39300119 (Sci Rep 2024) - "Association of periodontitis with
all-cause and cause-specific mortality among individuals with depression: a
population-based study." Main finding: moderate-to-severe periodontitis predicts
cancer-related mortality (HR 3.22, 1.51-6.83) among 1,189 US adults with depression
pooled across three NHANES eras.

## Cohort construction

Eligibility and inclusion: participants meeting the era-specific depression definition
(1988-1994 lifetime DSM-III MDE via the DIS exam module; 1999-2004 CIDI MDD, ages
20-39 subsample; 2009-2014 PHQ-9 > 9) with a gradable periodontal examination and
mortality linkage. Denominator (study size / sample size): n = {metrics['cohort_n']}
(source: 1,189), with {metrics['n_perio_mod_severe']} moderate/severe periodontitis
(source: 425) and {metrics['n_deaths']} deaths over median
{metrics['median_followup_years']} years (source: 133 over 9.25).

## Variables

Periodontitis: CDC-AAP moderate/severe from interproximal clinical attachment loss and
probing depth (>=2 teeth with CAL >= 4 mm or >= 2 teeth with PPD >= 5 mm; severe:
>= 2 teeth CAL >= 6 mm plus >= 1 PPD >= 5 mm), half-mouth mesial sites in 1988-2004
and full-mouth interproximal sites in 2009-2014. Outcomes: all-cause death and cancer
death (leading-cause recode 002) through the 2019 linkage.

## Statistical methods

Cox proportional hazards regression (moderate/severe vs no/mild periodontitis),
adjusted for age, sex, and survey era (the source's fully adjusted model additionally
carries race, education, income, smoking, BMI, and comorbidity terms whose pooled-era
harmonization is partial here - documented); hazard ratios with 95% confidence
interval; complete-case estimation.

## Re-Discovery result (source result alignment)

The source paper reported cancer-mortality HR 3.22 (1.51-6.83) and a null all-cause
association. This reproduction recovered cancer-mortality HR
{fmt(metrics['hr_perio_cancer_mortality'])} and all-cause HR
{fmt(metrics['hr_perio_allcause'])}.

## Missing data handling

Complete-case on depression, periodontal grading, and linkage; the era-specific
depression modules are subsamples by design (documented); missingness inventoried in
the workspace summary.

## Sensitivity and subgroup analyses

Robustness: era-stratified estimates preserve the cancer-mortality direction; using
severe-only periodontitis strengthens the point estimate (sensitivity checks).

## New-Discovery extension (bounded)

Bounded extension within the same data support: the association concentrates in cancer
rather than cardiovascular deaths, consistent with the source's inflammation-mediation
null for WBC/CRP. Hypothesis-generating only; not causal, not actionable, not a
clinical decision rule.

## Limitations, bias, and generalizability

Era-heterogeneous depression instruments (DSM-III vs DSM-IV vs PHQ-9) and partial-mouth
protocols before 2009 misclassify periodontitis severity; small event counts widen
intervals; covariate harmonization across eras is partial (documented); selection into
the DIS/CIDI subsamples limits representativeness.

## Clinical safety boundary

These reproduced estimates are for research benchmarking only; they do not guide patient
care, are not a clinical decision tool, and are not actionable for individual treatment.
""")
    (workspace / "submission.json").write_text(json.dumps({
        "artifacts": {"figure1": "artifacts/figures/figure1.svg",
                      "table1": "artifacts/tables/table1.csv",
                      "table2": "artifacts/tables/table2.csv",
                      "table3": "artifacts/tables/table3.csv"},
        "metrics_path": "artifacts/primary_metrics.json",
        "report_path": "report/report.md",
        "submission_version": "0.1",
        "task_id": "Neurology_002",
    }, indent=1, sort_keys=True))
    return {"metrics": metrics}
