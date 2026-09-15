from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "tasks" / "Endocrinology_001" / "data" / "source_manifest.json"

COMPONENT_COLUMNS = {
    "DEMO": [
        "SEQN",
        "RIDAGEYR",
        "RIAGENDR",
        "RIDRETH1",
        "DMDEDUC2",
        "INDFMPIR",
        "RIDEXPRG",
        "WTMEC2YR",
        "SDMVPSU",
        "SDMVSTRA",
    ],
    "BMX": ["SEQN", "BMXBMI", "BMXWAIST"],
    "BPX": [
        "SEQN",
        "BPXSY1",
        "BPXSY2",
        "BPXSY3",
        "BPXSY4",
        "BPXDI1",
        "BPXDI2",
        "BPXDI3",
        "BPXDI4",
    ],
    "BPQ": ["SEQN", "BPQ050A"],
    "DIQ": ["SEQN", "DIQ010"],
    "MCQ": ["SEQN", "MCQ160A", "MCQ160B", "MCQ160C", "MCQ160D"],
    "SMQ": ["SEQN", "SMQ020", "SMQ040"],
    "PAQ": ["SEQN", "PAQ650", "PAQ655", "PAD660", "PAQ665", "PAQ670", "PAD675"],
}

BP_SYSTOLIC_COLS = ["BPXSY1", "BPXSY2", "BPXSY3", "BPXSY4"]
BP_DIASTOLIC_COLS = ["BPXDI1", "BPXDI2", "BPXDI3", "BPXDI4"]
XPT_SUFFIXES = (".xpt", ".XPT", ".csv", ".CSV")


def load_source_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_component_path(input_dir: str | Path, expected_filename: str) -> Path:
    root = Path(input_dir)
    exact_candidates = [
        root / expected_filename,
        root / expected_filename.upper(),
        root / expected_filename.lower(),
    ]
    stem = Path(expected_filename).stem
    suffix_candidates = [root / f"{stem}{suffix}" for suffix in XPT_SUFFIXES]

    for candidate in [*exact_candidates, *suffix_candidates]:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Could not find component file for {expected_filename} in {root}")


def read_component(path: str | Path) -> pd.DataFrame:
    resolved = Path(path)
    if resolved.suffix.lower() == ".xpt":
        frame = pd.read_sas(resolved, format="xport")
    elif resolved.suffix.lower() == ".csv":
        frame = pd.read_csv(resolved)
    else:
        raise ValueError(f"Unsupported component file format: {resolved.suffix}")

    frame.columns = [str(column).upper() for column in frame.columns]
    return frame


def select_component_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    selected = frame.copy()
    for column in columns:
        if column not in selected.columns:
            selected[column] = pd.NA
    selected = selected[columns].copy()
    selected["SEQN"] = pd.to_numeric(selected["SEQN"], errors="coerce").astype("Int64")
    for column in columns:
        if column != "SEQN":
            selected[column] = pd.to_numeric(selected[column], errors="coerce")
    return selected


def load_component(input_dir: str | Path, expected_filename: str, columns: list[str], cycle_label: str) -> pd.DataFrame:
    path = resolve_component_path(input_dir, expected_filename)
    frame = read_component(path)
    frame = select_component_columns(frame, columns)
    frame["cycle_code"] = Path(expected_filename).stem.split("_")[-1].upper()
    frame["cycle_label"] = cycle_label
    return frame


def load_all_components(
    input_dir: str | Path,
    manifest: dict,
) -> dict[str, pd.DataFrame]:
    by_prefix: dict[str, list[dict]] = {prefix: [] for prefix in COMPONENT_COLUMNS}
    for component in manifest.get("components", []):
        prefix = Path(component["file"]).stem.split("_")[0].upper()
        if prefix in by_prefix:
            by_prefix[prefix].append(component)

    loaded: dict[str, pd.DataFrame] = {}
    for prefix, columns in COMPONENT_COLUMNS.items():
        entries = sorted(by_prefix[prefix], key=lambda item: item["cycle"])
        if not entries:
            raise ValueError(f"Source manifest is missing entries for component {prefix}")

        frames = [
            load_component(
                input_dir=input_dir,
                expected_filename=entry["file"],
                columns=columns,
                cycle_label=entry["cycle"],
            )
            for entry in entries
        ]
        loaded[prefix] = pd.concat(frames, ignore_index=True, sort=False)
    return loaded


def merge_components(components: dict[str, pd.DataFrame]) -> pd.DataFrame:
    merged = components["DEMO"].copy()
    merge_keys = ["SEQN", "cycle_code"]
    for prefix in ["BMX", "BPX", "BPQ", "DIQ", "MCQ", "SMQ", "PAQ"]:
        right = components[prefix].drop(columns=["cycle_label"], errors="ignore")
        merged = merged.merge(right, on=merge_keys, how="left", validate="one_to_one")
    return merged


def derive_age_group(age_years: pd.Series) -> pd.Series:
    labels = pd.Series(pd.NA, index=age_years.index, dtype="string")
    labels.loc[(age_years >= 18) & (age_years < 40)] = "18-39"
    labels.loc[(age_years >= 40) & (age_years < 60)] = "40-59"
    labels.loc[(age_years >= 60) & (age_years < 80)] = "60-79"
    labels.loc[age_years >= 80] = "80+"
    return labels


def derive_sex(series: pd.Series) -> pd.Series:
    mapped = pd.Series(pd.NA, index=series.index, dtype="string")
    mapped.loc[series == 1] = "male"
    mapped.loc[series == 2] = "female"
    return mapped


def derive_race_ethnicity(series: pd.Series) -> pd.Series:
    mapped = pd.Series(pd.NA, index=series.index, dtype="string")
    mapped.loc[series.isin([1, 2])] = "hispanic"
    mapped.loc[series == 3] = "non_hispanic_white"
    mapped.loc[series == 4] = "non_hispanic_black"
    mapped.loc[series == 5] = "other"
    return mapped


def derive_education(series: pd.Series) -> pd.Series:
    mapped = pd.Series(pd.NA, index=series.index, dtype="string")
    mapped.loc[series.isin([1, 2])] = "less_than_high_school"
    mapped.loc[series == 3] = "high_school"
    mapped.loc[series.isin([4, 5])] = "more_than_high_school"
    return mapped


def derive_income_group(series: pd.Series) -> pd.Series:
    mapped = pd.Series(pd.NA, index=series.index, dtype="string")
    mapped.loc[series < 1.0] = "below_1.0"
    mapped.loc[series >= 1.0] = "at_or_above_1.0"
    return mapped


def derive_binary_flag(series: pd.Series, yes_codes: set[int], no_codes: set[int]) -> pd.Series:
    result = pd.Series(pd.NA, index=series.index, dtype="Int64")
    result.loc[series.isin(yes_codes)] = 1
    result.loc[series.isin(no_codes)] = 0
    return result


def derive_cvd_flag(frame: pd.DataFrame) -> pd.Series:
    cvd_columns = ["MCQ160A", "MCQ160B", "MCQ160C", "MCQ160D"]
    values = frame[cvd_columns]
    result = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    any_yes = values.eq(1).any(axis=1)
    any_no = values.eq(2).any(axis=1)
    result.loc[any_yes] = 1
    result.loc[~any_yes & any_no] = 0
    return result


def derive_smoking_status(smoked_100: pd.Series, current_smoking: pd.Series) -> pd.Series:
    status = pd.Series(pd.NA, index=smoked_100.index, dtype="string")
    status.loc[smoked_100 == 2] = "never"
    status.loc[(smoked_100 == 1) & (current_smoking.isin([1, 2]))] = "current"
    status.loc[(smoked_100 == 1) & (current_smoking == 3)] = "former"
    return status


def activity_minutes(flag: pd.Series, days: pd.Series, minutes: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=flag.index, dtype="float64")
    result.loc[flag == 2] = 0.0
    yes_mask = flag == 1
    result.loc[yes_mask] = days.loc[yes_mask] * minutes.loc[yes_mask]
    return result


def derive_ltpa_minutes_and_group(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    vigorous = activity_minutes(frame["PAQ650"], frame["PAQ655"], frame["PAD660"])
    moderate = activity_minutes(frame["PAQ665"], frame["PAQ670"], frame["PAD675"])

    total_minutes = vigorous.fillna(0.0) + moderate.fillna(0.0)
    has_information = vigorous.notna() | moderate.notna()
    total_minutes = total_minutes.where(has_information, np.nan)

    category = pd.Series(pd.NA, index=frame.index, dtype="string")
    category.loc[has_information & (total_minutes == 0)] = "none"
    category.loc[(total_minutes > 0) & (total_minutes < 300)] = "0_to_<300"
    category.loc[total_minutes >= 300] = ">=300"
    return total_minutes, category


def derive_abdominal_obesity_flag(waist: pd.Series, sex_code: pd.Series) -> pd.Series:
    result = pd.Series(pd.NA, index=waist.index, dtype="Int64")
    male = sex_code == 1
    female = sex_code == 2
    result.loc[male & waist.notna()] = (waist.loc[male & waist.notna()] >= 102.0).astype("Int64")
    result.loc[female & waist.notna()] = (waist.loc[female & waist.notna()] >= 88.0).astype("Int64")
    return result


def derive_bmi_category(bmi: pd.Series) -> pd.Series:
    result = pd.Series(pd.NA, index=bmi.index, dtype="string")
    result.loc[bmi < 25.0] = "normal_or_underweight"
    result.loc[(bmi >= 25.0) & (bmi < 30.0)] = "overweight"
    result.loc[bmi >= 30.0] = "obese"
    return result


def derive_joint_group(abdominal_obesity_flag: pd.Series, bmi_category: pd.Series) -> pd.Series:
    result = pd.Series(pd.NA, index=bmi_category.index, dtype="string")
    no_abd = abdominal_obesity_flag == 0
    yes_abd = abdominal_obesity_flag == 1
    for category in ["normal_or_underweight", "overweight", "obese"]:
        result.loc[no_abd & (bmi_category == category)] = f"no_abd_{category}"
        result.loc[yes_abd & (bmi_category == category)] = f"yes_abd_{category}"
    return result


def derive_bp_means(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    sbp_values = frame[BP_SYSTOLIC_COLS]
    dbp_values = frame[BP_DIASTOLIC_COLS]
    sbp_mean = sbp_values.mean(axis=1, skipna=True)
    dbp_mean = dbp_values.mean(axis=1, skipna=True)
    sbp_count = sbp_values.notna().sum(axis=1).astype("Int64")
    dbp_count = dbp_values.notna().sum(axis=1).astype("Int64")
    sbp_mean = sbp_mean.where(sbp_count > 0, np.nan)
    dbp_mean = dbp_mean.where(dbp_count > 0, np.nan)
    return sbp_mean, dbp_mean, sbp_count, dbp_count


def derive_hypertension_flag(mean_sbp: pd.Series, mean_dbp: pd.Series, medication_response: pd.Series) -> pd.Series:
    result = pd.Series(pd.NA, index=mean_sbp.index, dtype="Int64")
    elevated_bp = (mean_sbp >= 140.0) | (mean_dbp >= 90.0)
    medication_yes = medication_response == 1
    normal_bp_with_measurement = mean_sbp.notna() & mean_dbp.notna() & ~elevated_bp
    result.loc[elevated_bp | medication_yes] = 1
    result.loc[normal_bp_with_measurement & ~medication_yes] = 0
    return result


def derive_variables(frame: pd.DataFrame) -> pd.DataFrame:
    derived = frame.copy()
    derived["combined_4yr_mec_weight"] = derived["WTMEC2YR"] / 2.0
    derived["age_group"] = derive_age_group(derived["RIDAGEYR"])
    derived["sex"] = derive_sex(derived["RIAGENDR"])
    derived["race_ethnicity"] = derive_race_ethnicity(derived["RIDRETH1"])
    derived["education"] = derive_education(derived["DMDEDUC2"])
    derived["income_poverty_ratio_group"] = derive_income_group(derived["INDFMPIR"])
    derived["diabetes_flag"] = derive_binary_flag(derived["DIQ010"], yes_codes={1}, no_codes={2, 3})
    derived["cardiovascular_disease_flag"] = derive_cvd_flag(derived)
    derived["smoking_status"] = derive_smoking_status(derived["SMQ020"], derived["SMQ040"])
    derived["ltpa_minutes_per_week"], derived["ltpa_group"] = derive_ltpa_minutes_and_group(derived)
    derived["abdominal_obesity_flag"] = derive_abdominal_obesity_flag(derived["BMXWAIST"], derived["RIAGENDR"])
    derived["bmi_category"] = derive_bmi_category(derived["BMXBMI"])
    derived["bmi_abdominal_obesity_group"] = derive_joint_group(
        derived["abdominal_obesity_flag"],
        derived["bmi_category"],
    )
    (
        derived["mean_sbp"],
        derived["mean_dbp"],
        derived["sbp_reading_count"],
        derived["dbp_reading_count"],
    ) = derive_bp_means(derived)
    derived["bp_medication_current_flag"] = derive_binary_flag(derived["BPQ050A"], yes_codes={1}, no_codes={2})
    derived["hypertension_flag"] = derive_hypertension_flag(
        derived["mean_sbp"],
        derived["mean_dbp"],
        derived["BPQ050A"],
    )
    return derived


def build_analytic_mask(frame: pd.DataFrame) -> pd.Series:
    adults = frame["RIDAGEYR"] >= 18
    pregnant = frame["RIDEXPRG"] == 1
    missing_waist = frame["BMXWAIST"].isna()
    missing_bmi = frame["BMXBMI"].isna()
    missing_bp = frame["mean_sbp"].isna() | frame["mean_dbp"].isna()
    return adults & ~pregnant & ~missing_waist & ~missing_bmi & ~missing_bp


def build_cohort_summary(frame: pd.DataFrame, analytic_mask: pd.Series) -> dict:
    all_rows = len(frame)
    adults_mask = frame["RIDAGEYR"] >= 18
    adults = frame.loc[adults_mask]
    pregnant_mask = adults["RIDEXPRG"] == 1
    after_pregnancy = adults.loc[~pregnant_mask]
    missing_waist_mask = after_pregnancy["BMXWAIST"].isna()
    after_waist = after_pregnancy.loc[~missing_waist_mask]
    missing_bmi_mask = after_waist["BMXBMI"].isna()
    after_bmi = after_waist.loc[~missing_bmi_mask]
    missing_bp_mask = after_bmi["mean_sbp"].isna() | after_bmi["mean_dbp"].isna()
    final = after_bmi.loc[~missing_bp_mask]

    return {
        "n_input_rows": all_rows,
        "n_adults": int(adults_mask.sum()),
        "n_excluded_under_18": int(all_rows - adults_mask.sum()),
        "n_excluded_pregnant": int(pregnant_mask.sum()),
        "n_excluded_missing_waist": int(missing_waist_mask.sum()),
        "n_excluded_missing_bmi": int(missing_bmi_mask.sum()),
        "n_excluded_missing_blood_pressure": int(missing_bp_mask.sum()),
        "n_final_analytic": int(analytic_mask.sum()),
        "final_cycle_counts": {
            cycle: int(count)
            for cycle, count in final["cycle_label"].value_counts(dropna=False).sort_index().items()
        },
        "unweighted_abdominal_obesity_prevalence_pct": round(float(final["abdominal_obesity_flag"].mean() * 100), 4)
        if len(final) > 0
        else None,
        "unweighted_hypertension_prevalence_pct": round(float(final["hypertension_flag"].mean() * 100), 4)
        if len(final) > 0
        else None,
    }


def prepare_public_nhanes_001_extract(
    input_dir: str | Path,
    output_csv: str | Path,
    output_summary_json: str | Path,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
) -> tuple[pd.DataFrame, dict]:
    manifest = load_source_manifest(manifest_path)
    components = load_all_components(input_dir, manifest)
    merged = merge_components(components)
    derived = derive_variables(merged)
    analytic_mask = build_analytic_mask(derived)
    analytic = derived.loc[analytic_mask].copy()
    analytic = analytic.sort_values(["cycle_code", "SEQN"]).reset_index(drop=True)

    output_csv_path = Path(output_csv)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    analytic.to_csv(output_csv_path, index=False)

    summary = build_cohort_summary(derived, analytic_mask)
    summary["input_dir"] = str(Path(input_dir).resolve())
    summary["output_csv"] = str(output_csv_path.resolve())
    summary["manifest_path"] = str(Path(manifest_path).resolve())
    summary["columns"] = list(analytic.columns)

    summary_path = Path(output_summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    return analytic, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prepare_public_nhanes_001.py",
        description="Prepare the analytic extract for ClinicalRepBench task Endocrinology_001.",
    )
    parser.add_argument("input_dir", help="Directory containing the staged NHANES component files.")
    parser.add_argument(
        "--output-csv",
        default="out/public_nhanes_001_analytic_extract.csv",
        help="Path to write the prepared analytic extract CSV.",
    )
    parser.add_argument(
        "--output-summary-json",
        default="out/public_nhanes_001_cohort_summary.json",
        help="Path to write the cohort summary JSON.",
    )
    parser.add_argument(
        "--manifest-path",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Path to the source manifest JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    analytic, summary = prepare_public_nhanes_001_extract(
        input_dir=args.input_dir,
        output_csv=args.output_csv,
        output_summary_json=args.output_summary_json,
        manifest_path=args.manifest_path,
    )

    print(
        json.dumps(
            {
                "rows": len(analytic),
                "output_csv": str(Path(args.output_csv).resolve()),
                "output_summary_json": str(Path(args.output_summary_json).resolve()),
                "n_final_analytic": summary["n_final_analytic"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
