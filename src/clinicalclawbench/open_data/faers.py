from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


OPENFDA_EVENT_ENDPOINT = "https://api.fda.gov/drug/event.json"
DOWNLOAD_TIMEOUT_SECONDS = 90


def plan_downloads(manifest: dict) -> list[dict]:
    query = manifest.get("openfda", {})
    return [
        {
            "provider": "faers_openfda",
            "endpoint": OPENFDA_EVENT_ENDPOINT,
            "search": query.get("search", ""),
            "limit": int(query.get("limit", 1000)),
            "file": "openfda_faers_events.json",
        }
    ]


def download_events(search: str, output_path: str | Path, limit: int = 1000) -> Path:
    params = {"search": search, "limit": str(limit)}
    url = f"{OPENFDA_EVENT_ENDPOINT}?{urllib.parse.urlencode(params)}"
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ClinicalClawBench-open-data-prep/0.3"},
    )
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        destination.write_bytes(response.read())
    return destination


def flatten_events_json(path: str | Path) -> pd.DataFrame:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows: list[dict] = []
    for event in payload.get("results", []):
        patient = event.get("patient") or {}
        reactions = patient.get("reaction") or []
        drugs = patient.get("drug") or []
        primary_drug = drugs[0] if drugs else {}
        rows.append(
            {
                "safetyreportid": event.get("safetyreportid"),
                "receivedate": event.get("receivedate"),
                "serious": event.get("serious"),
                "seriousnessdeath": event.get("seriousnessdeath"),
                "patientsex": patient.get("patientsex"),
                "reaction_terms": "|".join(r.get("reactionmeddrapt", "") for r in reactions),
                "primary_drug": primary_drug.get("medicinalproduct"),
                "drug_characterization": primary_drug.get("drugcharacterization"),
            }
        )
    return pd.DataFrame(rows)


def prepare_manifest(manifest: dict, workspace: str | Path, download: bool = False, cache_dir: str | Path | None = None) -> dict:
    workspace_root = Path(workspace)
    source_root = workspace_root / "data" / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    item = plan_downloads(manifest)[0]
    cache_root = Path(cache_dir) if cache_dir is not None else source_root
    raw_path = cache_root / item["file"]
    if download and not raw_path.exists():
        download_events(item["search"], raw_path, limit=item["limit"])
    if not raw_path.exists():
        raise FileNotFoundError("No openFDA FAERS JSON file found; run with download=True or stage data/source/openfda_faers_events.json")

    extract = flatten_events_json(raw_path)
    output_csv = workspace_root / "data" / "analytic_extract.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    extract.to_csv(output_csv, index=False)
    return {
        "task_id": manifest["task_id"],
        "dataset": manifest["dataset"],
        "rows": int(len(extract)),
        "output_csv": str(output_csv.resolve()),
    }
