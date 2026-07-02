"""Writes the metadata half of the open format: <name>.meta.json.

The JSON is deliberately human-readable and self-describing. It carries the
format name/version, the asset, the list of sensors, a pointer to the Parquet
file that holds the measurements, and provenance about how it was produced.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..model import FORMAT_NAME, FORMAT_VERSION, Dataset


def build_metadata(dataset: Dataset, measurements_filename: str) -> dict:
    """Return the metadata as a plain dict (useful for tests / embedding)."""
    asset = asdict(dataset.asset)
    if asset.get("location") is None:
        asset.pop("location", None)

    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset,
        "sensors": [asdict(s) for s in dataset.sensors],
        "measurements_file": measurements_filename,
        "measurement_count": len(dataset.measurements),
        "source": dataset.source,
    }


def write_json(dataset: Dataset, path: str, measurements_filename: str) -> Path:
    """Write the metadata JSON to `path`. Returns the written path."""
    meta = build_metadata(dataset, measurements_filename)
    p = Path(path)
    with p.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return p
