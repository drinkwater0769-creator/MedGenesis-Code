"""Neurology_000 crude-outcome development profile, not a paper-complete model."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from clinicalrepbench.ukb_io import iter_projected, verify_prepared

CUTOFF = pd.Timestamp("2020-06-01")
SPECIAL_DATES = {"1900-01-01", "1901-01-01", "1902-02-02", "1903-03-03", "1909-09-09", "2037-07-07"}
DEMENTIA_PREFIXES = ("F00", "F01", "F02", "F03")


def parse_dates(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    text = text.mask(text.str.slice(0, 10).isin(SPECIAL_DATES))
    return pd.to_datetime(text, errors="coerce", format="mixed").astype("datetime64[ns]")


def dementia_codes(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True).str.startswith(DEMENTIA_PREFIXES)


def paired_death(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Attach causes only to their own registry date, including same-day duplicates."""
    date_cols = sorted(c for c in frame if c.startswith("40000-"))
    if not date_cols:
        return (pd.Series(pd.NaT, index=frame.index),
                pd.Series(False, index=frame.index), pd.Series(False, index=frame.index))
    parsed = {c: parse_dates(frame[c]) for c in date_cols}
    earliest = pd.DataFrame(parsed).min(axis=1)
    primary = pd.Series(False, index=frame.index)
    mention = pd.Series(False, index=frame.index)
    for col, dates in parsed.items():
        suffix = col.split("-", 1)[1]
        same_date = dates.eq(earliest) & dates.notna()
        p = dementia_codes(frame["40001-" + suffix])
        primary |= same_date & p
        mention |= same_date & p
        instance = suffix.split(".")[0]
        for secondary in [c for c in frame if c.startswith("40002-" + instance + ".")]:
            mention |= same_date & dementia_codes(frame[secondary])
    return earliest, primary, mention


def endpoint_masks(baseline: pd.Series, death: pd.Series, hospital: pd.Series):
    landmark = baseline + np.timedelta64(730, "D")
    eligible = (baseline.notna() & (landmark < CUTOFF)
                & (death.isna() | (death > landmark))
                & (hospital.isna() | (hospital > landmark)))
    mortality_end = death.fillna(CUTOFF).clip(upper=CUTOFF)
    incident = hospital.notna() & (hospital > landmark) & (hospital <= mortality_end)
    incidence_end = mortality_end.where(~incident, hospital)
    return eligible, incident, landmark, mortality_end, incidence_end


def suppressed_count(value: int):
    return int(value) if value >= 5 else None


def run_neurology_diagnostic(prepared: str | Path, task_dir: str | Path,
                             output: str | Path, chunksize: int = 5000) -> dict:
    root, output = Path(prepared), Path(output)
    repo = Path(__file__).resolve().parents[2]
    if output.resolve() == repo or repo in output.resolve().parents:
        raise ValueError("Diagnostic outputs must stay outside the public repository")
    if output.exists():
        raise FileExistsError("Diagnostic output already exists")
    checked = verify_prepared(root, task_dir)
    if not checked["ok"]:
        raise ValueError("Prepared input validation failed: " + "; ".join(checked["errors"]))
    manifest = checked["provenance"]
    if manifest["profile"] != "neurology000-crude-v1" or manifest["task_id"] != "Neurology_000":
        raise ValueError("Diagnostic requires the Neurology_000 crude profile")
    tables = manifest["tables"]
    base = None
    baseline_fields = {"31", "53", "21022", "46", "47", "20002"}
    for table in tables:
        cols = [c for c in table["columns"] if c != "eid" and c.split("-", 1)[0] in baseline_fields]
        if not cols:
            continue
        part = pd.concat(iter_projected(root / table["path"], ["eid"] + cols, chunksize), ignore_index=True).set_index("eid", verify_integrity=True)
        base = part if base is None else base.join(part, how="left", validate="one_to_one")
    if base is None or base.empty:
        raise ValueError("No baseline participants")
    baseline = parse_dates(base["53-0.0"])
    age = pd.to_numeric(base["21022-0.0"], errors="coerce")
    left = pd.to_numeric(base["46-0.0"], errors="coerce")
    right = pd.to_numeric(base["47-0.0"], errors="coerce")
    bilateral = left.notna() & right.notna() & np.isfinite(left) & np.isfinite(right) & (left > 0) & (right > 0)
    self_report = pd.Series(False, index=base.index)
    for col in [c for c in base if c.startswith("20002-0.")]:
        self_report |= pd.to_numeric(base[col], errors="coerce").eq(1263).fillna(False)
    hospital = pd.Series(pd.NaT, index=base.index, dtype="datetime64[ns]")
    death = hospital.copy()
    primary = pd.Series(False, index=base.index)
    mention = primary.copy()
    for table in tables:
        columns = [c for c in table["columns"] if c.startswith(("41270-", "41280-", "40000-", "40001-", "40002-"))]
        if not columns:
            continue
        for chunk in iter_projected(root / table["path"], ["eid"] + columns, chunksize):
            chunk = chunk.set_index("eid", verify_integrity=True)
            first = pd.Series(pd.NaT, index=chunk.index, dtype="datetime64[ns]")
            for col in [c for c in columns if c.startswith("41270-")]:
                date_col = "41280-" + col.split("-", 1)[1]
                candidate = parse_dates(chunk[date_col]).where(dementia_codes(chunk[col]))
                first = pd.concat([first, candidate], axis=1).min(axis=1)
            if any(c.startswith("41270-") for c in columns):
                hospital.loc[chunk.index] = first
            if any(c.startswith("40000-") for c in columns):
                d, p, m = paired_death(chunk)
                death.loc[chunk.index], primary.loc[chunk.index], mention.loc[chunk.index] = d, p, m
    risk, incident, landmark, mortality_end, incidence_end = endpoint_masks(baseline, death, hospital)
    eligible = risk & age.between(40, 80).fillna(False) & bilateral.fillna(False) & ~self_report
    primary_event = primary & death.notna() & (death > landmark) & (death <= CUTOFF)
    mention_event = mention & death.notna() & (death > landmark) & (death <= CUTOFF)
    n = int(eligible.sum())
    inc_days = (incidence_end - landmark).dt.days[eligible]
    mort_days = (mortality_end - landmark).dt.days[eligible]
    if (inc_days < 0).any() or (mort_days < 0).any():
        raise ValueError("Invalid negative follow-up")
    inc_events = int((incident & eligible).sum())
    primary_events = int((primary_event & eligible).sum())
    mention_events = int((mention_event & eligible).sum())
    def rate(events, days):
        years = float(days.sum()) / 365.25
        return round(events / years * 1000, 6) if events >= 5 and n >= 5 and years > 0 else None
    result = {
        "task_id": "Neurology_000", "profile": "neurology000-crude-v1", "development_only": True,
        "formal_score_eligible": False, "full_paper_reproduction": False,
        "scope": "Bilateral grip, a fixed 730-day landmark, paired hospital/registry dementia outcomes and crude aggregate rates only",
        "censor_date": "2020-06-01", "source_release": manifest["source_release"],
        "withdrawal_status": manifest["withdrawal_status"], "minimum_reported_count": 5,
        "metrics": {"cohort_n": suppressed_count(n), "n_incident_dementia": suppressed_count(inc_events),
                    "n_dementia_deaths": suppressed_count(primary_events)},
        "diagnostic_rates": {"incident_per_1000py": rate(inc_events, inc_days),
                             "underlying_mortality_per_1000py": rate(primary_events, mort_days),
                             "any_mention_mortality_per_1000py": rate(mention_events, mort_days)},
        "not_estimated": ["adjusted hazard ratios", "paper quintiles", "interactions", "causal effects"],
        "limitations": ["Historical snapshot equivalence and withdrawals are not independently verified.",
                        "The baseline self-report exclusion code and paired hospital endpoint define a declared development slice.",
                        "These crude metrics are not equivalent to the paper's full adjusted analysis."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return {"ok": True, "profile": result["profile"], "formal_score_eligible": False,
            "notice": "Diagnostic completed; results remain in the governed output location"}
