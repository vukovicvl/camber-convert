"""CSV reader.

Reads a "tidy" (long-format) CSV where each row is one reading. This matches
the shape Camber already uses for its own CSV import, so the two stay aligned.

Required columns (case-insensitive, common aliases accepted):
    timestamp     ISO-8601, e.g. 2026-01-15T09:30:00Z
    sensor_id     identifier of the sensor
    metric_type   what is being measured, e.g. acceleration, displacement
    value         numeric reading
    unit          physical unit, e.g. m/s^2, mm

Optional columns (used to describe the asset/sensors when present):
    asset_id, asset_name, sensor_type, axis, serial_number

If no asset columns are present, all readings are attached to a single default
asset. Sensor definitions are inferred from the rows.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from ..model import Asset, Dataset, Measurement, Sensor
from .base import register

# Accept a few common header spellings -> canonical name.
_ALIASES = {
    "timestamp": "timestamp",
    "time": "timestamp",
    "datetime": "timestamp",
    "sensor_id": "sensor_id",
    "sensor": "sensor_id",
    "sensorid": "sensor_id",
    "metric_type": "metric_type",
    "metric": "metric_type",
    "measurement": "metric_type",
    "value": "value",
    "reading": "value",
    "unit": "unit",
    "units": "unit",
    "asset_id": "asset_id",
    "asset_name": "asset_name",
    "sensor_type": "sensor_type",
    "axis": "axis",
    "serial_number": "serial_number",
}

_REQUIRED = {"timestamp", "sensor_id", "metric_type", "value", "unit"}


class CsvFormatError(Exception):
    """Raised when the CSV is missing required columns or has bad values."""


def _parse_timestamp(raw: str) -> datetime:
    s = raw.strip()
    # Support a trailing 'Z' (UTC) which older fromisoformat() rejects.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:  # assume naive timestamps are UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@register(".csv")
def read_csv(path: str) -> Dataset:
    p = Path(path)
    with p.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise CsvFormatError("CSV is empty or has no header row.")

        # Map real headers -> canonical names.
        colmap = {}
        for h in reader.fieldnames:
            canon = _ALIASES.get(h.strip().lower())
            if canon:
                colmap[h] = canon

        present = set(colmap.values())
        missing = _REQUIRED - present
        if missing:
            raise CsvFormatError(
                "CSV missing required columns: "
                + ", ".join(sorted(missing))
                + f". Found: {', '.join(reader.fieldnames)}"
            )

        measurements: list[Measurement] = []
        sensors: dict[str, Sensor] = {}
        asset_id = "asset-1"
        asset_name = "Unnamed asset"

        for i, row in enumerate(reader, start=2):  # row 1 is the header
            r = {colmap[k]: (v or "").strip() for k, v in row.items() if k in colmap}
            if not any(r.values()):
                continue  # skip blank lines

            try:
                ts = _parse_timestamp(r["timestamp"])
                value = float(r["value"])
            except (ValueError, KeyError) as e:
                raise CsvFormatError(f"Row {i}: could not parse ({e}).") from e

            sid = r["sensor_id"]
            if "asset_id" in r and r["asset_id"]:
                asset_id = r["asset_id"]
            if "asset_name" in r and r["asset_name"]:
                asset_name = r["asset_name"]

            if sid not in sensors:
                sensors[sid] = Sensor(
                    id=sid,
                    asset_id=asset_id,
                    sensor_type=r.get("sensor_type") or "unknown",
                    unit=r["unit"],
                    serial_number=r.get("serial_number") or None,
                    axis=r.get("axis") or None,
                )

            measurements.append(
                Measurement(
                    timestamp=ts,
                    sensor_id=sid,
                    metric_type=r["metric_type"],
                    value=value,
                    unit=r["unit"],
                )
            )

    if not measurements:
        raise CsvFormatError("CSV has a header but no data rows.")

    asset = Asset(id=asset_id, name=asset_name, type="bridge")
    # point every sensor at the resolved asset id
    for s in sensors.values():
        s.asset_id = asset_id

    return Dataset(
        asset=asset,
        sensors=list(sensors.values()),
        measurements=measurements,
        source={"reader": "csv", "original_file": p.name},
    )
