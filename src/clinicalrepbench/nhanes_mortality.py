"""NCHS public-use Linked Mortality File (LMF, 2019 release) support for
continuous-NHANES mortality tasks.

File layout (fixed width, one row per survey participant):
  cols 1-14  publicid (NHANES: SEQN, left-aligned)
  col  15    eligstat (1 = eligible for linkage)
  col  16    mortstat (0 = assumed alive, 1 = assumed deceased)
  cols 17-19 ucod_leading (3-digit leading cause recode; 001 = diseases of
             heart, 002 = malignant neoplasms, 005 = cerebrovascular diseases)
  col  20    diabetes flag, col 21 hypertension flag (multiple-cause)
  cols 43-45 permth_int (months from interview), cols 46-48 permth_exm
             (months from MEC examination)
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

LMF_BASE = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/linked_mortality"

LMF_FILES = {
    "1999-2000": "NHANES_1999_2000_MORT_2019_PUBLIC.dat",
    "2001-2002": "NHANES_2001_2002_MORT_2019_PUBLIC.dat",
    "2003-2004": "NHANES_2003_2004_MORT_2019_PUBLIC.dat",
    "2005-2006": "NHANES_2005_2006_MORT_2019_PUBLIC.dat",
    "2007-2008": "NHANES_2007_2008_MORT_2019_PUBLIC.dat",
    "2009-2010": "NHANES_2009_2010_MORT_2019_PUBLIC.dat",
    "2011-2012": "NHANES_2011_2012_MORT_2019_PUBLIC.dat",
    "2013-2014": "NHANES_2013_2014_MORT_2019_PUBLIC.dat",
    "2015-2016": "NHANES_2015_2016_MORT_2019_PUBLIC.dat",
    "2017-2018": "NHANES_2017_2018_MORT_2019_PUBLIC.dat",
}

UCOD_HEART = 1
UCOD_CEREBROVASCULAR = 5


def _to_int(s: str) -> float:
    s = s.strip()
    if not s or s == ".":
        return np.nan
    try:
        return float(int(s))
    except ValueError:
        return np.nan


def parse_lmf(path: str | Path) -> pd.DataFrame:
    rows = []
    for line in Path(path).read_text().splitlines():
        if len(line) < 16:
            continue
        rows.append({
            "SEQN": _to_int(line[0:14]),
            "eligstat": _to_int(line[14:15]),
            "mortstat": _to_int(line[15:16]),
            "ucod_leading": _to_int(line[16:19]),
            "permth_int": _to_int(line[42:45]),
            "permth_exm": _to_int(line[45:48]),
        })
    frame = pd.DataFrame(rows)
    return frame[frame["SEQN"].notna()].copy()


def stage_lmf(cycles: list[str], cache_dir: str | Path, download: bool = True) -> pd.DataFrame:
    """Download (or reuse cached) LMF files for the given cycles and return the
    concatenated mortality frame."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    frames = []
    for cycle in cycles:
        name = LMF_FILES[cycle]
        local = cache / name
        if not local.exists() or local.stat().st_size == 0:
            if not download:
                raise FileNotFoundError(f"LMF file missing and download disabled: {local}")
            urllib.request.urlretrieve(f"{LMF_BASE}/{name}", local)
        part = parse_lmf(local)
        part["cycle"] = cycle
        frames.append(part)
    return pd.concat(frames, ignore_index=True)
