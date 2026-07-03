"""CSV reader -- dispatches between two shapes and stays locale-robust.

Two CSV layouts are supported:

* **tidy / long** -- one row per reading, columns
  ``timestamp, sensor_id, metric_type, value, unit`` (+ optional asset/sensor
  description columns). This is the shape Camber's own export and the open format
  use, so the two stay aligned.
* **wide / multi-channel** -- one row per timestamp, one column per channel. This
  is what most data-acquisition systems export. It is handled by
  :mod:`.wide_csv_reader` under a named :class:`~.wide_csv_reader.ImportProfile`.

``read_csv`` decides which shape a file is: if a wide profile matches the header
(or one is passed explicitly) it melts the wide file; otherwise it reads it as
tidy. Delimiter, decimal separator, encoding, and timestamp format are sniffed
(:mod:`._csvutil`) so a file from any locale -- ``;``-separated, decimal-comma,
UTF-16, ``dd.mm.yyyy`` dates -- reads correctly instead of silently corrupting.

Required tidy columns (case-insensitive, common aliases accepted):
    timestamp, sensor_id, metric_type, value, unit
Optional tidy columns:
    asset_id, asset_name, sensor_type, axis, serial_number
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from ..model import Asset, Dataset, Measurement, Sensor
from ._csvutil import (
    CsvFormatError,
    Dialect,
    norm,
    parse_number,
    parse_timestamp,
    read_header,
    sniff_dialect,
)
from .base import register
from .wide_csv_reader import (
    ImportProfile,
    build_asset_and_sensors,
    find_profile,
    iter_measurements,
    load_profiles,
    match_profile,
    read_wide,
    resolve_channels,
)

# Accept a few common header spellings -> canonical name.
_ALIASES = {
    "timestamp": "timestamp", "time": "timestamp", "datetime": "timestamp",
    "sensor_id": "sensor_id", "sensor": "sensor_id", "sensorid": "sensor_id",
    "metric_type": "metric_type", "metric": "metric_type", "measurement": "metric_type",
    "value": "value", "reading": "value",
    "unit": "unit", "units": "unit",
    "asset_id": "asset_id", "asset_name": "asset_name",
    "sensor_type": "sensor_type", "axis": "axis", "serial_number": "serial_number",
}

_REQUIRED = {"timestamp", "sensor_id", "metric_type", "value", "unit"}


@dataclass
class CsvInspection:
    """What a file looks like, without importing it -- drives an import preview."""

    kind: str  # "wide" | "tidy"
    profile_name: str | None
    dialect: Dialect
    fieldnames: list[str]
    asset: Asset
    sensors: list[Sensor]
    preview: list[Measurement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Tidy reader
# --------------------------------------------------------------------------- #

def _tidy_colmap(fieldnames: list[str]) -> dict[str, str]:
    colmap = {}
    for h in fieldnames:
        canon = _ALIASES.get(norm(h))
        if canon:
            colmap[h] = canon
    return colmap


def _read_tidy(path: str, dialect: Dialect) -> Dataset:
    with open(path, "r", encoding=dialect.encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter=dialect.delimiter)
        if reader.fieldnames is None:
            raise CsvFormatError("CSV is empty or has no header row.")
        colmap = _tidy_colmap(list(reader.fieldnames))
        missing = _REQUIRED - set(colmap.values())
        if missing:
            raise CsvFormatError(
                "CSV missing required columns: " + ", ".join(sorted(missing))
                + f". Found: {', '.join(reader.fieldnames)}"
            )

        measurements: list[Measurement] = []
        sensors: dict[str, Sensor] = {}
        asset_id, asset_name = "asset-1", "Unnamed asset"

        for i, row in enumerate(reader, start=2):
            r = {colmap[k]: (v or "").strip() for k, v in row.items() if k in colmap}
            if not any(r.values()):
                continue
            try:
                ts = parse_timestamp(r["timestamp"], dialect.timestamp_format)
                value = parse_number(r["value"], dialect.decimal)
            except CsvFormatError as e:
                raise CsvFormatError(f"Row {i}: {e}") from e
            if value is None:
                raise CsvFormatError(f"Row {i}: could not parse value {r['value']!r}.")

            sid = r["sensor_id"]
            asset_id = r.get("asset_id") or asset_id
            asset_name = r.get("asset_name") or asset_name
            if sid not in sensors:
                sensors[sid] = Sensor(
                    id=sid, asset_id=asset_id,
                    sensor_type=r.get("sensor_type") or "unknown",
                    unit=r["unit"], serial_number=r.get("serial_number") or None,
                    axis=r.get("axis") or None,
                )
            measurements.append(Measurement(
                timestamp=ts, sensor_id=sid, metric_type=r["metric_type"],
                value=value, unit=r["unit"],
            ))

    if not measurements:
        raise CsvFormatError("CSV has a header but no data rows.")
    asset = Asset(id=asset_id, name=asset_name, type="bridge")
    for s in sensors.values():
        s.asset_id = asset_id
    return Dataset(asset=asset, sensors=list(sensors.values()),
                   measurements=measurements,
                   source={"reader": "csv", "original_file": Path(path).name})


# --------------------------------------------------------------------------- #
# Dispatch + inspection
# --------------------------------------------------------------------------- #

def _resolve_profile(path: str, profile, user_dir: str | None) -> ImportProfile | None:
    """Return the wide profile to use, or None to read as tidy."""
    if isinstance(profile, ImportProfile):
        return profile
    if isinstance(profile, str):
        p = find_profile(profile, user_dir)
        if p is None:
            raise CsvFormatError(f"unknown import profile: {profile!r}")
        return p
    # auto: match a wide profile by header signature
    dialect0 = sniff_dialect(path)
    header = read_header(path, dialect0)
    return match_profile(header, load_profiles(user_dir))


@register(".csv")
def read_csv(path: str, profile=None, user_dir: str | None = None) -> Dataset:
    """Read a CSV into a :class:`Dataset`, wide or tidy.

    ``profile`` may be an :class:`ImportProfile`, a profile name, or None (auto).
    """
    prof = _resolve_profile(path, profile, user_dir)
    if prof is not None:
        return read_wide(path, prof)
    return _read_tidy(path, sniff_dialect(path))


def _locale_warnings(dialect: Dialect, sample_ts: str | None) -> list[str]:
    warns = []
    if dialect.decimal == ",":
        warns.append("Decimal comma detected: values like '44,87' are read as 44.87. "
                     "Check the preview values look right.")
    if sample_ts and "/" in sample_ts and not dialect.timestamp_format:
        warns.append(f"Slash date {sample_ts!r}: day/month order is ambiguous. "
                     "If dates look wrong, pin 'timestamp_format' in the profile.")
    return warns


def inspect_csv(path: str, profile=None, user_dir: str | None = None,
                sample: int = 10) -> CsvInspection:
    """Describe a CSV (shape, dialect, asset/sensors, a few melted rows) without
    importing it. Feeds an in-app preview so a mis-detected locale or layout is
    caught by eye before anything is written."""
    dialect0 = sniff_dialect(path)
    header = read_header(path, dialect0)
    prof = _resolve_profile(path, profile, user_dir)

    if prof is not None:  # wide
        dialect = sniff_dialect(path, delimiter=prof.delimiter, decimal=prof.decimal,
                                timestamp_format=prof.timestamp_format)
        channels = resolve_channels(prof, header)
        asset, sensors = build_asset_and_sensors(prof, channels)
        preview: list[Measurement] = []
        for m in iter_measurements(path, prof, dialect):
            preview.append(m)
            if len(preview) >= sample:
                break
        warns = _locale_warnings(dialect, _first_value(path, dialect, prof.time_column))
        if not preview:
            warns.append("No readings parsed from the first rows (all blank or sentinel?).")
        return CsvInspection("wide", prof.name, dialect, header, asset, sensors, preview, warns)

    # tidy
    dialect = dialect0
    colmap = _tidy_colmap(header)
    missing = _REQUIRED - set(colmap.values())
    if missing:
        names = ", ".join(p.name for p in load_profiles(user_dir)) or "(none)"
        raise CsvFormatError(
            "CSV is neither a known wide layout nor tidy. Missing tidy columns: "
            f"{', '.join(sorted(missing))}. Found: {', '.join(header)}. "
            f"Available wide profiles: {names}."
        )
    ds = _read_tidy(path, dialect)  # small preview cost; files that reach here are tidy
    warns = _locale_warnings(dialect, _first_value(path, dialect, "timestamp", colmap))
    return CsvInspection("tidy", None, dialect, header, ds.asset, ds.sensors,
                         ds.measurements[:sample], warns)


def stream_measurements(path: str, profile=None, user_dir: str | None = None):
    """Yield :class:`Measurement` objects one at a time (wide files stream; tidy
    files are read then yielded). Lets a caller bulk-insert millions of rows
    without materialising them all in memory."""
    prof = _resolve_profile(path, profile, user_dir)
    if prof is not None:
        yield from iter_measurements(path, prof)
    else:
        yield from _read_tidy(path, sniff_dialect(path)).measurements


def _first_value(path: str, dialect: Dialect, column: str,
                 colmap: dict | None = None) -> str | None:
    """Return the raw value of ``column`` from the first data row (for warnings)."""
    target = column
    if colmap:
        inv = {v: k for k, v in colmap.items()}
        target = inv.get(column, column)
    with open(path, "r", encoding=dialect.encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter=dialect.delimiter)
        for row in reader:
            return (row.get(target) or "").strip() or None
    return None
