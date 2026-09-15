from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from clinicalrepbench.public_nhanes_001_prep import prepare_public_nhanes_001_extract


AGE_ADJUSTMENT_WEIGHTS = {
    "18_39": 0.396579,
    "40_59": 0.371795,
    "60_plus": 0.231626,
}

TABLE1_SPECS = [
    ("overall", "Overall", None),
    ("sex", "Sex", ["male", "female"]),
    ("analysis_age_group3", "Age group", ["18_39", "40_59", "60_plus"]),
    (
        "race_ethnicity",
        "Race and ethnicity",
        ["non_hispanic_white", "non_hispanic_black", "hispanic", "other", "missing"],
    ),
    (
        "education",
        "Education",
        ["less_than_high_school", "high_school", "more_than_high_school", "missing"],
    ),
    (
        "income_poverty_ratio_group",
        "Income to poverty ratio",
        ["below_1.0", "at_or_above_1.0", "missing"],
    ),
    ("diabetes_status", "Diabetes", ["no", "yes", "missing"]),
    ("cardiovascular_disease_status", "Cardiovascular disease", ["no", "yes", "missing"]),
    ("smoking_status", "Smoking status", ["never", "former", "current", "missing"]),
    ("ltpa_group", "Leisure-time physical activity", ["none", "0_to_<300", ">=300", "missing"]),
]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _display_label(value: object) -> str:
    mapping = {
        "18_39": "18-39",
        "40_59": "40-59",
        "60_plus": "60+",
        "normal_or_underweight": "Normal or underweight",
        "overweight": "Overweight",
        "obese": "Obese",
        "no_abd_normal_or_underweight": "No abdominal obesity + normal/underweight",
        "yes_abd_normal_or_underweight": "Abdominal obesity + normal/underweight",
        "no_abd_overweight": "No abdominal obesity + overweight",
        "yes_abd_overweight": "Abdominal obesity + overweight",
        "no_abd_obese": "No abdominal obesity + obese",
        "yes_abd_obese": "Abdominal obesity + obese",
        "non_hispanic_white": "Non-Hispanic white",
        "non_hispanic_black": "Non-Hispanic black",
        "hispanic": "Hispanic",
        "other": "Other",
        "less_than_high_school": "Less than high school",
        "high_school": "High school",
        "more_than_high_school": "More than high school",
        "below_1.0": "Below 1.0",
        "at_or_above_1.0": "At least 1.0",
        "none": "None",
        "0_to_<300": "0 to <300 min/week",
        ">=300": ">=300 min/week",
        "missing": "Missing",
        "yes": "Yes",
        "no": "No",
        "male": "Male",
        "female": "Female",
    }
    if value is None:
        return "Overall"
    string_value = str(value)
    return mapping.get(string_value, string_value)


def _load_or_prepare_extract(workspace: Path) -> tuple[pd.DataFrame, Path, dict | None]:
    candidate_paths = [
        workspace / "data" / "analytic_extract.csv",
        workspace / "data" / "public_nhanes_001_analytic_extract.csv",
        workspace / "outputs" / "prepared" / "public_nhanes_001_analytic_extract.csv",
    ]
    for candidate in candidate_paths:
        if candidate.exists():
            return pd.read_csv(candidate), candidate, None

    input_dir = workspace / "data"
    output_csv = workspace / "outputs" / "prepared" / "public_nhanes_001_analytic_extract.csv"
    output_summary = workspace / "outputs" / "prepared" / "public_nhanes_001_cohort_summary.json"
    analytic, summary = prepare_public_nhanes_001_extract(
        input_dir=input_dir,
        output_csv=output_csv,
        output_summary_json=output_summary,
    )
    return analytic, output_csv, summary


def _weighted_mean(series: pd.Series, weights: pd.Series) -> float:
    valid = series.notna() & weights.notna()
    if not valid.any():
        return math.nan
    values = pd.to_numeric(series.loc[valid], errors="coerce")
    valid = valid & values.notna()
    if not valid.any():
        return math.nan
    return float(np.average(values.loc[valid], weights=weights.loc[valid]))


def _weighted_binary_pct(frame: pd.DataFrame, outcome_col: str, weight_col: str) -> float:
    prevalence = _weighted_mean(frame[outcome_col], frame[weight_col])
    return float(prevalence * 100.0)


def _weighted_sum(series: pd.Series) -> float:
    valid = pd.to_numeric(series, errors="coerce").dropna()
    return float(valid.sum()) if not valid.empty else 0.0


def _clean_analysis_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["analysis_age_group3"] = np.select(
        [
            data["RIDAGEYR"] < 40,
            (data["RIDAGEYR"] >= 40) & (data["RIDAGEYR"] < 60),
            data["RIDAGEYR"] >= 60,
        ],
        ["18_39", "40_59", "60_plus"],
        default="missing",
    )

    for column in ["sex", "race_ethnicity", "education", "income_poverty_ratio_group", "smoking_status", "ltpa_group"]:
        data[column] = data[column].fillna("missing").astype(str)

    data["diabetes_status"] = data["diabetes_flag"].map({1: "yes", 0: "no"}).fillna("missing")
    data["cardiovascular_disease_status"] = data["cardiovascular_disease_flag"].map({1: "yes", 0: "no"}).fillna("missing")
    data["bmi_category"] = data["bmi_category"].fillna("missing").astype(str)
    data["bmi_abdominal_obesity_group"] = data["bmi_abdominal_obesity_group"].fillna("missing").astype(str)
    data["combined_4yr_mec_weight"] = pd.to_numeric(data["combined_4yr_mec_weight"], errors="coerce")
    data["hypertension_flag"] = pd.to_numeric(data["hypertension_flag"], errors="coerce")
    data["abdominal_obesity_flag"] = pd.to_numeric(data["abdominal_obesity_flag"], errors="coerce")
    return data


def build_table1(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    weights = data["combined_4yr_mec_weight"]
    for column, label, levels in TABLE1_SPECS:
        if column == "overall":
            subset = data
            rows.append(
                {
                    "characteristic": label,
                    "level": "Overall",
                    "unweighted_n": int(len(subset)),
                    "weighted_n": round(_weighted_sum(weights), 2),
                    "abdominal_obesity_prev_pct": round(_weighted_binary_pct(subset, "abdominal_obesity_flag", "combined_4yr_mec_weight"), 2),
                }
            )
            continue

        ordered_levels = levels or sorted(data[column].dropna().unique())
        for level in ordered_levels:
            subset = data.loc[data[column] == level]
            if subset.empty:
                continue
            rows.append(
                {
                    "characteristic": label,
                    "level": _display_label(level),
                    "unweighted_n": int(len(subset)),
                    "weighted_n": round(_weighted_sum(subset["combined_4yr_mec_weight"]), 2),
                    "abdominal_obesity_prev_pct": round(_weighted_binary_pct(subset, "abdominal_obesity_flag", "combined_4yr_mec_weight"), 2),
                }
            )
    return pd.DataFrame(rows)


def _age_adjusted_prevalence(data: pd.DataFrame, group_value: int) -> float:
    subset = data.loc[data["abdominal_obesity_flag"] == group_value]
    weighted_total = 0.0
    weight_sum = 0.0
    for age_group, std_weight in AGE_ADJUSTMENT_WEIGHTS.items():
        age_subset = subset.loc[subset["analysis_age_group3"] == age_group]
        if age_subset.empty:
            continue
        prevalence = _weighted_binary_pct(age_subset, "hypertension_flag", "combined_4yr_mec_weight")
        weighted_total += prevalence * std_weight
        weight_sum += std_weight
    if weight_sum == 0:
        return math.nan
    return weighted_total / weight_sum


def build_table2(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for group_value, group_label in [(0, "No abdominal obesity"), (1, "Abdominal obesity")]:
        subset = data.loc[data["abdominal_obesity_flag"] == group_value]
        for age_group in ["18_39", "40_59", "60_plus"]:
            age_subset = subset.loc[subset["analysis_age_group3"] == age_group]
            if age_subset.empty:
                continue
            rows.append(
                {
                    "abdominal_obesity_group": group_label,
                    "age_group": _display_label(age_group),
                    "estimate_type": "age_specific",
                    "unweighted_n": int(len(age_subset)),
                    "weighted_n": round(_weighted_sum(age_subset["combined_4yr_mec_weight"]), 2),
                    "hypertension_prev_pct": round(_weighted_binary_pct(age_subset, "hypertension_flag", "combined_4yr_mec_weight"), 2),
                }
            )

        rows.append(
            {
                "abdominal_obesity_group": group_label,
                "age_group": "Total",
                "estimate_type": "age_adjusted",
                "unweighted_n": int(len(subset)),
                "weighted_n": round(_weighted_sum(subset["combined_4yr_mec_weight"]), 2),
                "hypertension_prev_pct": round(_age_adjusted_prevalence(data, group_value), 2),
            }
        )
    return pd.DataFrame(rows)


def _preferred_reference(column: str) -> str:
    references = {
        "analysis_age_group3": "18_39",
        "sex": "male",
        "race_ethnicity": "non_hispanic_white",
        "education": "more_than_high_school",
        "income_poverty_ratio_group": "at_or_above_1.0",
        "diabetes_status": "no",
        "cardiovascular_disease_status": "no",
        "smoking_status": "never",
        "ltpa_group": ">=300",
        "bmi_category": "normal_or_underweight",
        "bmi_abdominal_obesity_group": "no_abd_normal_or_underweight",
    }
    return references[column]


def _categorical_term(data: pd.DataFrame, column: str) -> str:
    reference = _preferred_reference(column)
    if reference in set(data[column].dropna().astype(str)):
        return f"C({column}, Treatment(reference='{reference}'))"
    return f"C({column})"


def _fit_weighted_logit(formula: str, data: pd.DataFrame):
    model = smf.glm(
        formula=formula,
        data=data,
        family=sm.families.Binomial(),
        freq_weights=data["combined_4yr_mec_weight"],
    )
    return model.fit(maxiter=200, disp=0)


def _or_row(model_name: str, result, term: str, label: str) -> dict:
    beta = float(result.params[term])
    conf = result.conf_int().loc[term]
    return {
        "model": model_name,
        "term": label,
        "odds_ratio": round(float(np.exp(beta)), 4),
        "ci_lower": round(float(np.exp(conf.iloc[0])), 4),
        "ci_upper": round(float(np.exp(conf.iloc[1])), 4),
        "p_value": round(float(result.pvalues[term]), 6),
    }


def build_table3(data: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    covariates = [
        _categorical_term(data, "analysis_age_group3"),
        _categorical_term(data, "sex"),
        _categorical_term(data, "race_ethnicity"),
        _categorical_term(data, "education"),
        _categorical_term(data, "income_poverty_ratio_group"),
        _categorical_term(data, "diabetes_status"),
        _categorical_term(data, "cardiovascular_disease_status"),
        _categorical_term(data, "smoking_status"),
        _categorical_term(data, "ltpa_group"),
    ]
    covariate_formula = " + ".join(covariates)

    formula_model3 = (
        "hypertension_flag ~ abdominal_obesity_flag + "
        + _categorical_term(data, "bmi_category")
        + " + "
        + covariate_formula
    )
    result_model3 = _fit_weighted_logit(formula_model3, data)

    formula_model4 = (
        "hypertension_flag ~ "
        + _categorical_term(data, "bmi_abdominal_obesity_group")
        + " + "
        + covariate_formula
    )
    result_model4 = _fit_weighted_logit(formula_model4, data)

    model4_reference = _preferred_reference("bmi_abdominal_obesity_group")
    joint_prefix = f"C(bmi_abdominal_obesity_group, Treatment(reference='{model4_reference}'))"
    if joint_prefix not in " ".join(result_model4.params.index):
        joint_prefix = "C(bmi_abdominal_obesity_group)"

    rows = [
        _or_row("Model 3", result_model3, "abdominal_obesity_flag", "Abdominal obesity"),
        _or_row(
            "Model 4",
            result_model4,
            f"{joint_prefix}[T.yes_abd_normal_or_underweight]",
            "Abdominal obesity + normal/underweight",
        ),
        _or_row(
            "Model 4",
            result_model4,
            f"{joint_prefix}[T.yes_abd_overweight]",
            "Abdominal obesity + overweight",
        ),
        _or_row(
            "Model 4",
            result_model4,
            f"{joint_prefix}[T.yes_abd_obese]",
            "Abdominal obesity + obese",
        ),
    ]

    metrics = {
        "or_abd_obesity_model3": rows[0]["odds_ratio"],
        "or_abd_yes_normal_bmi_model4": rows[1]["odds_ratio"],
        "or_abd_yes_overweight_model4": rows[2]["odds_ratio"],
        "or_abd_yes_obese_model4": rows[3]["odds_ratio"],
    }
    return pd.DataFrame(rows), metrics


def _write_report(workspace: Path, metrics: dict, extract_path: Path, prep_summary: dict | None) -> None:
    summary_lines = []
    if prep_summary is not None:
        summary_lines.append(
            f"The analytic extract was prepared inside the workspace and retained {prep_summary['n_final_analytic']} participants."
        )
    else:
        summary_lines.append(f"The analysis used a prepared analytic extract located at `{extract_path.name}`.")

    report = f"""# NHANES Reference Report

## Methods

I analyzed the NHANES 2007-2008 and 2009-2010 adult cohort defined in the task specification.
Abdominal obesity was defined using sex-specific waist-circumference thresholds, and hypertension was defined using the mean of available blood-pressure readings or current blood-pressure medication use.
All descriptive estimates and logistic models used the combined 4-year MEC examination weights from the prepared analytic extract.
{summary_lines[0]}

## Re-Discovery

The final analytic cohort included {metrics['cohort_n']} participants.
The weighted prevalence of abdominal obesity was {metrics['abd_obesity_prev_pct']:.2f}%.
Age-adjusted hypertension prevalence was {metrics['htn_prev_abd_yes_pct']:.2f}% among participants with abdominal obesity and {metrics['htn_prev_abd_no_pct']:.2f}% among those without abdominal obesity.
In the covariate-adjusted model that included BMI category, the odds ratio for abdominal obesity was {metrics['or_abd_obesity_model3']:.2f}.
In the joint BMI and abdominal-obesity model, the odds ratios were {metrics['or_abd_yes_normal_bmi_model4']:.2f} for abdominal obesity with normal or underweight BMI, {metrics['or_abd_yes_overweight_model4']:.2f} for abdominal obesity with overweight BMI, and {metrics['or_abd_yes_obese_model4']:.2f} for abdominal obesity with obese BMI.

## New-Discovery

The prepared extract includes waist circumference, BMI, blood-pressure measurements, medication use, and demographic covariates, enabling a bounded extension that compares abdominal obesity against simpler anthropometric rules in the same NHANES cohort.

## Limitations

This reference implementation uses weighted generalized linear models rather than a full design-based survey regression package with Taylor-series variance estimation.
It is intended to provide a deterministic benchmark baseline for task execution and scoring, not a definitive reanalysis of the source publication.
The resulting point estimates should be interpreted as an implementation baseline and may require further calibration against the hidden evaluator pipeline.

## Clinical Safety

The results are population-level benchmark estimates and should not be used for individual diagnosis or treatment decisions.
"""
    report_path = workspace / "report" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def _write_manifest(workspace: Path) -> None:
    _write_json(
        workspace / "submission.json",
        {
            "submission_version": "0.1",
            "task_id": "Endocrinology_001",
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


def _write_figure(workspace: Path, metrics: dict) -> None:
    figure_dir = workspace / "artifacts" / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="680" height="180">
  <rect width="680" height="180" fill="white"/>
  <text x="24" y="34" font-family="Arial" font-size="18">Age-adjusted hypertension prevalence</text>
  <rect x="24" y="70" width="{max(metrics['htn_prev_abd_no_pct'] * 5, 1):.1f}" height="30" fill="#4C78A8"/>
  <text x="24" y="122" font-family="Arial" font-size="14">No abdominal obesity: {metrics['htn_prev_abd_no_pct']:.2f}%</text>
  <rect x="24" y="132" width="{max(metrics['htn_prev_abd_yes_pct'] * 5, 1):.1f}" height="30" fill="#F58518"/>
  <text x="24" y="174" font-family="Arial" font-size="14">Abdominal obesity: {metrics['htn_prev_abd_yes_pct']:.2f}%</text>
</svg>
"""
    (figure_dir / "figure1.svg").write_text(svg, encoding="utf-8")


def run_public_nhanes_001_reference(workspace: str | Path) -> dict:
    workspace_path = Path(workspace).resolve()
    analytic, extract_path, prep_summary = _load_or_prepare_extract(workspace_path)
    data = _clean_analysis_frame(analytic)

    table1 = build_table1(data)
    table2 = build_table2(data)
    table3, table3_metrics = build_table3(data)

    metrics = {
        "cohort_n": int(len(data)),
        "abd_obesity_prev_pct": round(_weighted_binary_pct(data, "abdominal_obesity_flag", "combined_4yr_mec_weight"), 4),
        "htn_prev_abd_yes_pct": round(_age_adjusted_prevalence(data, 1), 4),
        "htn_prev_abd_no_pct": round(_age_adjusted_prevalence(data, 0), 4),
        **table3_metrics,
    }

    artifacts_dir = workspace_path / "artifacts"
    tables_dir = artifacts_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    table1.to_csv(tables_dir / "table1.csv", index=False)
    table2.to_csv(tables_dir / "table2.csv", index=False)
    table3.to_csv(tables_dir / "table3.csv", index=False)
    _write_json(artifacts_dir / "primary_metrics.json", {"metrics": metrics})
    _write_figure(workspace_path, metrics)
    _write_report(workspace_path, metrics, extract_path, prep_summary)
    _write_manifest(workspace_path)
    return metrics
