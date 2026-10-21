"""Read losslessly compressed measurement files by capture ID."""
from pathlib import Path
import gzip
import json

ROOT = Path(__file__).resolve().parent
INDEX = {r["capture_id"]: r for r in json.loads((ROOT / "raw_index.json").read_text(encoding="utf-8"))}

def raw_path(capture_id, name="samples.csv"):
    return ROOT / INDEX[capture_id]["measurement_files"][name]["path"]

def open_raw(capture_id, name="samples.csv"):
    return gzip.open(raw_path(capture_id, name), "rt", encoding="utf-8-sig", newline="")
