"""NHANES III (1988-1994) fixed-width file support.

The NHANES III public-use files (adult.dat, exam.dat, lab.dat) are fixed-width
ASCII with column positions documented in the companion SAS input files
(adult.sas, exam.sas, lab.sas). This module parses the SAS ``INPUT`` section to
recover positions and reads only the requested variables.

The NHANES III public-use 2019 linked mortality file
(NHANES_III_MORT_2019_PUBLIC.dat) shares the layout of the continuous-NHANES
LMF files and is parsed by clinicalrepbench.nhanes_mortality.parse_lmf.
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

NH3_BASE = "https://wwwn.cdc.gov/nchs/data/nhanes3"

NH3_FILES = {
    "adult": ("1a/adult.dat", "1a/adult.sas"),
    "exam": ("1a/exam.dat", "1a/exam.sas"),
    "lab": ("1a/lab.dat", "1a/lab.sas"),
}


def parse_sas_positions(sas_path: str | Path) -> dict[str, tuple[int, int]]:
    """Parse the INPUT section of an NHANES III SAS reader; returns
    {VARNAME: (start, end)} with 1-based inclusive columns."""
    text = Path(sas_path).read_text(errors="ignore")
    m = re.search(r"\bINPUT\b(.*?);", text, re.S | re.I)
    if not m:
        raise ValueError(f"No INPUT section found in {sas_path}")
    positions: dict[str, tuple[int, int]] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        mm = re.match(r"([A-Z0-9_]+)\s+\$?\s*(\d+)\s*-\s*(\d+)", line)
        if mm:
            positions[mm.group(1)] = (int(mm.group(2)), int(mm.group(3)))
            continue
        mm = re.match(r"([A-Z0-9_]+)\s+\$?\s*(\d+)\s*$", line)
        if mm:
            pos = int(mm.group(2))
            positions[mm.group(1)] = (pos, pos)
    return positions


def stage_nh3(cache_dir: str | Path, parts: list[str], download: bool = True) -> dict[str, Path]:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for part in parts:
        dat_rel, sas_rel = NH3_FILES[part]
        for rel in (dat_rel, sas_rel):
            local = cache / Path(rel).name
            if not local.exists() or local.stat().st_size == 0:
                if not download:
                    raise FileNotFoundError(f"missing {local}")
                urllib.request.urlretrieve(f"{NH3_BASE}/{rel}", local)
        out[part] = cache / Path(dat_rel).name
    return out


def read_nh3(dat_path: str | Path, sas_path: str | Path, variables: list[str]) -> pd.DataFrame:
    """Read selected variables from an NHANES III fixed-width file."""
    pos = parse_sas_positions(sas_path)
    missing = [v for v in variables if v.upper() not in pos]
    if missing:
        raise KeyError(f"variables not in {Path(sas_path).name}: {missing}")
    wanted = [(v.upper(), pos[v.upper()]) for v in dict.fromkeys([v.upper() for v in variables])]
    if "SEQN" not in [w[0] for w in wanted]:
        wanted.insert(0, ("SEQN", pos["SEQN"]))
    colspecs = [(start - 1, end) for _, (start, end) in wanted]
    names = [name for name, _ in wanted]
    frame = pd.read_fwf(dat_path, colspecs=colspecs, names=names, header=None,
                        dtype=str, encoding="latin-1")
    for col in names:
        frame[col] = pd.to_numeric(frame[col].str.strip().replace("", np.nan), errors="coerce")
    return frame


def apply_bounds(frame: pd.DataFrame, bounds: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Blank NHANES III sentinel/missing codes by variable-specific plausibility
    bounds (fields of 8s / 9s encode blank-but-applicable / unknown)."""
    for col, (lo, hi) in bounds.items():
        if col in frame.columns:
            frame[col] = frame[col].where((frame[col] >= lo) & (frame[col] <= hi))
    return frame
