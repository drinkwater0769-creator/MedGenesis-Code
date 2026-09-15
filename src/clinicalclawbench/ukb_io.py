"""Portable, read-only UKB input inspection and governed local projections.

No participant values are returned by inspection. Projection outputs contain
participant rows and must remain in the user's authorized data environment.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd


def canonical_column(name: str) -> str:
    name = str(name).strip().lstrip("\ufeff")
    if name.lower() in {"eid", "participant.eid"}:
        return "eid"
    name = name.removeprefix("participant.")
    if re.fullmatch(r"\d+-\d+\.\d+", name):
        return name
    match = re.fullmatch(r"(?:f\.)?(\d+)\.(\d+)\.(\d+)", name)
    if not match:
        match = re.fullmatch(r"p(\d+)_i(\d+)(?:_a(\d+))?", name)
    if match:
        field, instance, array = match.groups()
        return f"{field}-{instance}.{array or '0'}"
    return name


def source_header(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        raw = pq.read_schema(path).names
        delimiter = None
    else:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            first = handle.readline()
        delimiter = "\t" if first.count("\t") > first.count(",") else ","
        raw = next(csv.reader([first], delimiter=delimiter))
    canonical = [canonical_column(name) for name in raw]
    if len(set(canonical)) != len(canonical):
        raise ValueError("Duplicate or colliding column names in an input source")
    if "eid" not in canonical:
        raise ValueError("Input source is missing the participant key column eid")
    return {"mapping": dict(zip(canonical, raw)), "delimiter": delimiter,
            "header_sha256": hashlib.sha256(json.dumps(raw).encode()).hexdigest()}


def iter_projected(path: str | Path, columns: list[str], chunksize: int = 5000):
    if chunksize < 1:
        raise ValueError("chunksize must be positive")
    path = Path(path)
    header = source_header(path)
    absent = sorted(set(columns) - set(header["mapping"]))
    if absent:
        raise ValueError("Missing requested columns: " + ", ".join(absent))
    raw = [header["mapping"][name] for name in columns]
    rename = dict(zip(raw, columns))
    if path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        for batch in pq.ParquetFile(path).iter_batches(batch_size=chunksize, columns=raw):
            yield batch.to_pandas().rename(columns=rename)[columns].astype("string")
    else:
        with pd.read_csv(path, sep=header["delimiter"], usecols=raw,
                         dtype="string", chunksize=chunksize, keep_default_na=False) as reader:
            for frame in reader:
                yield frame.rename(columns=rename)[columns]


def profile_fields(contract: dict, profile: str) -> list[dict]:
    if profile not in contract.get("supported_execution_profiles", []):
        raise ValueError("Profile is not advertised by this task source contract")
    if profile == "neurology000-crude-v1" and contract["task_id"] == "Neurology_000":
        ids = ["31", "53", "21022", "46", "47", "20002", "41270", "41280", "40000", "40001", "40002"]
        return [{"field_id": fid, "instances": "all" if fid in {"40000", "40001", "40002"} else [0]}
                for fid in ids]
    if profile != "ukb-candidate-input-v1" or contract["source_class"] == "repository":
        raise ValueError("Unsupported profile for this task; consult its source contract")
    return contract["candidate_ukb_fields"]


def inspect_inputs(task_dir: str | Path, inputs: list[str | Path], profile: str) -> dict:
    contract = json.loads((Path(task_dir) / "data/source_contract.json").read_text())
    fields = profile_fields(contract, profile)
    if not fields:
        raise ValueError("No complete candidate field inventory is available for this task")
    if not inputs:
        raise ValueError("At least one source is required")
    headers = [source_header(p) for p in inputs]
    selected = [[] for _ in inputs]
    missing = []
    owners = {}
    for field in fields:
        found = False
        for i, header in enumerate(headers):
            for col in header["mapping"]:
                match = re.fullmatch(r"(\d+)-(\d+)\.(\d+)", col)
                if not match or match[1] != field["field_id"]:
                    continue
                instances = field.get("instances", [0])
                if instances != "all" and int(match[2]) not in instances:
                    continue
                if col in owners and owners[col] != i:
                    raise ValueError("Overlapping data columns across inputs: " + col + "; supply disjoint exports")
                owners[col] = i
                selected[i].append(col)
                found = True
        if not found:
            missing.append(field["field_id"])
    # Matched array coordinates are essential: never silently zip unrelated cells.
    chosen = set(owners)
    pair_errors = []
    if "41270" in {f["field_id"] for f in fields}:
        codes = {c.split("-", 1)[1] for c in chosen if c.startswith("41270-")}
        dates = {c.split("-", 1)[1] for c in chosen if c.startswith("41280-")}
        if codes != dates:
            pair_errors.append("Hospital ICD codes/dates have unmatched instance-array coordinates")
        if any(owners.get("41270-" + c) != owners.get("41280-" + c) for c in codes & dates):
            pair_errors.append("Paired hospital codes/dates must be in the same input table")
    if profile == "neurology000-crude-v1":
        death = {c.split("-", 1)[1] for c in chosen if c.startswith("40000-")}
        primary = {c.split("-", 1)[1] for c in chosen if c.startswith("40001-")}
        if death != primary:
            pair_errors.append("Death dates/underlying causes have unmatched registry instances")
        registry_owners = {owners[c] for c in chosen if c.startswith(("40000-", "40001-", "40002-"))}
        if len(registry_owners) > 1:
            pair_errors.append("Death registry instances and causes must be in one table")
        for field in ["31", "53", "21022", "46", "47"]:
            if f"{field}-0.0" not in chosen:
                pair_errors.append(f"Required exact baseline coordinate absent: {field}-0.0")
    return {"task_id": contract["task_id"], "profile": profile,
            "input_headers_ok": not missing and not pair_errors,
            "missing_field_ids": sorted(missing, key=int), "pairing_errors": pair_errors,
            "sources": [{"source_id": f"source_{i+1}", "header_sha256": h["header_sha256"],
                         "selected_columns": ["eid"] + sorted(set(cols))}
                        for i, (h, cols) in enumerate(zip(headers, selected)) if cols],
            "source_indices": [i for i, cols in enumerate(selected) if cols],
            "formal_score_eligible": False,
            "scope": "Header availability only; no proof of scientific definition or source-snapshot equivalence"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_inputs(task_dir: str | Path, inputs: list[str | Path], output: str | Path,
                   profile: str, source_release: str, withdrawal_status: str,
                   chunksize: int = 5000) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq
    task_dir, output = Path(task_dir).resolve(), Path(output).resolve()
    repo_root = Path(__file__).resolve().parents[2]
    if output == repo_root or repo_root in output.parents:
        raise ValueError("Participant data output must be outside the public repository")
    if output.exists():
        raise FileExistsError("Output already exists; select a new governed output directory")
    if not source_release.strip() or withdrawal_status not in {"applied", "not_verified"}:
        raise ValueError("Declare source release and withdrawal status explicitly")
    inspection = inspect_inputs(task_dir, inputs, profile)
    if not inspection["input_headers_ok"]:
        raise ValueError("Source inspection failed: " + json.dumps({k: inspection[k] for k in ["missing_field_ids", "pairing_errors"]}))
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".ukb-prepare-", dir=output.parent))
    try:
        reference_keys = None
        tables = []
        for source, index in zip(inspection["sources"], inspection["source_indices"]):
            path = temp / (source["source_id"] + ".parquet")
            schema = pa.schema([(c, pa.string()) for c in source["selected_columns"]])
            seen = set()
            with pq.ParquetWriter(path, schema) as writer:
                for frame in iter_projected(inputs[index], source["selected_columns"], chunksize):
                    keys = frame["eid"].str.strip()
                    if keys.isna().any() or keys.eq("").any() or keys.duplicated().any() or seen.intersection(keys):
                        raise ValueError("Missing or duplicate participant keys; no identifier values are displayed")
                    frame["eid"] = keys
                    seen.update(keys.tolist())
                    writer.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False))
            if not seen:
                raise ValueError("Empty input source")
            if reference_keys is not None and reference_keys != seen:
                raise ValueError("Participant key sets differ across source tables; no implicit inner join is allowed")
            reference_keys = seen
            tables.append({"path": path.name, "rows": len(seen), "columns": source["selected_columns"],
                           "sha256": file_sha256(path), "input_header_sha256": source["header_sha256"]})
        manifest = {"schema_version": "clinicalrep.governed-input.v1", "task_id": inspection["task_id"],
                    "profile": profile, "source_release": source_release, "withdrawal_status": withdrawal_status,
                    "created_date": date.today().isoformat(), "contract_sha256": file_sha256(task_dir / "data/source_contract.json"),
                    "participant_level_data": True, "may_upload": False, "formal_score_eligible": False,
                    "tables": tables}
        (temp / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
        temp.rename(output)
        return {"ok": True, "task_id": inspection["task_id"], "profile": profile,
                "table_count": len(tables), "formal_score_eligible": False,
                "notice": "Governed participant-level projection created; do not upload it"}
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def verify_prepared(prepared_dir: str | Path, task_dir: str | Path) -> dict:
    root, task = Path(prepared_dir).resolve(), Path(task_dir)
    manifest = json.loads((root / "provenance.json").read_text())
    errors = []
    info = json.loads((task / "task_info.json").read_text())
    if manifest.get("task_id") != info["task_id"]:
        errors.append("task_id mismatch")
    if manifest.get("contract_sha256") != file_sha256(task / "data/source_contract.json"):
        errors.append("source contract has changed")
    contract = json.loads((task / "data/source_contract.json").read_text())
    if manifest.get("schema_version") != "clinicalrep.governed-input.v1":
        errors.append("unsupported provenance schema")
    if manifest.get("profile") not in contract.get("supported_execution_profiles", []):
        errors.append("unsupported execution profile")
    if not str(manifest.get("source_release", "")).strip():
        errors.append("missing source release declaration")
    if manifest.get("withdrawal_status") not in {"applied", "not_verified"}:
        errors.append("missing or invalid withdrawals declaration")
    if manifest.get("formal_score_eligible") is not False or manifest.get("may_upload") is not False:
        errors.append("governed input must remain private and development-only")
    if not manifest.get("tables"):
        errors.append("no input tables")
    for table in manifest.get("tables", []):
        path = (root / table["path"]).resolve()
        if root not in path.parents or not path.is_file():
            errors.append("missing or unsafe table path")
        elif file_sha256(path) != table.get("sha256"):
            errors.append("projected table hash mismatch")
    return {"ok": not errors, "errors": errors, "task_id": info["task_id"],
            "formal_score_eligible": False, "provenance": manifest}
