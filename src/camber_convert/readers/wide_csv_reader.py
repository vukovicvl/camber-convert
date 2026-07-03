"""Wide / multi-channel CSV reader (profile-driven).

Many data-acquisition systems export "wide" CSVs: one row per timestamp, and one
*column* per measurement channel::

    ,ts,id,ch_1,ch_2,...,ch_30,fileid,event
    0,2023-02-20T03:10:53,7396779155,444.28,204.03,...,-1000000.0,62018,none
    1,2023-02-20T03:10:53.005000,7396779156,444.02,...,   ...    ,62018,none

The open format is *tidy* (one row per reading), so this reader **melts** the wide
layout: each channel cell becomes one :class:`Measurement`. Which column is the
timestamp, which columns are channels, what each channel means, and what value
stands for "no data" all vary by vendor -- so they are described by a named
:class:`ImportProfile` rather than hard-coded. Adding support for a new vendor's
layout is then just another profile, not new parsing code.

Locale handling (delimiter / decimal / encoding / timestamp) is delegated to
:mod:`._csvutil`, so a wide CSV from any country parses the same way.
"""

from __future__ import annotations

import csv
import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

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


@dataclass
class ChannelSpec:
    """One source column mapped to a sensor + what it measures.

    ``column`` is the header name in the file (e.g. ``"ch_1"``). The rest is the
    legend: what physical quantity that channel carries. When a channel is
    discovered by glob and has no explicit spec, sensible generic defaults are
    used (metric_type == column name, empty unit) so the file still imports.
    """

    column: str
    sensor_id: str | None = None      # stable id; defaults to the column name
    sensor_type: str = "unknown"
    metric_type: str | None = None    # defaults to the column name
    unit: str = ""
    axis: str | None = None

    def resolved_id(self) -> str:
        return self.sensor_id or self.column

    def resolved_metric(self) -> str:
        return self.metric_type or self.column


@dataclass
class ImportProfile:
    """A reusable description of one vendor's wide-CSV layout."""

    name: str
    # Auto-selection: a profile matches a file when every column named here is
    # present in the header (compared case/space-insensitively).
    match_columns: list[str] = field(default_factory=list)
    time_column: str = "timestamp"
    # Columns to never treat as channels (index col, row id, file id, flags...).
    ignore_columns: list[str] = field(default_factory=list)
    # Glob that auto-discovers channel columns (e.g. "ch_*"). Discovered columns
    # not covered by an explicit `channels` entry get generic defaults.
    channel_glob: str | None = None
    channels: list[ChannelSpec] = field(default_factory=list)
    # Values that mean "no reading" and are dropped (e.g. a -1000000.0 sentinel).
    sentinels: list[float] = field(default_factory=list)
    # Locale overrides; None => auto-sniff.
    delimiter: str | None = None
    decimal: str | None = None
    timestamp_format: str | None = None
    # Describe the resulting asset.
    asset_id: str = "asset-1"
    asset_name: str = "Imported asset"
    asset_type: str = "bridge"

    # ---- construction from JSON so new layouts can be dropped in as data ----
    @classmethod
    def from_dict(cls, d: dict) -> "ImportProfile":
        chans = [ChannelSpec(**c) if not isinstance(c, ChannelSpec) else c
                 for c in d.get("channels", [])]
        return cls(
            name=d["name"],
            match_columns=list(d.get("match_columns", [])),
            time_column=d.get("time_column", "timestamp"),
            ignore_columns=list(d.get("ignore_columns", [])),
            channel_glob=d.get("channel_glob"),
            channels=chans,
            sentinels=[float(x) for x in d.get("sentinels", [])],
            delimiter=d.get("delimiter"),
            decimal=d.get("decimal"),
            timestamp_format=d.get("timestamp_format"),
            asset_id=d.get("asset_id", "asset-1"),
            asset_name=d.get("asset_name", "Imported asset"),
            asset_type=d.get("asset_type", "bridge"),
        )


# --------------------------------------------------------------------------- #
# Built-in profiles. New vendor layouts can be added here or loaded from JSON
# files via load_profiles(user_dir=...).
# --------------------------------------------------------------------------- #

_GENERIC_WIDE = ImportProfile(
    name="generic-wide",
    # Matches nothing on its own (no distinctive columns); used only when the
    # caller selects it explicitly for an arbitrary wide file.
    match_columns=[],
    time_column="timestamp",
    ignore_columns=["", "id", "index", "fileid", "file_id", "event", "flag"],
    channel_glob="ch_*",
    channels=[],
    sentinels=[-1000000.0],
    asset_name="Imported asset",
)

BUILTIN_PROFILES: list[ImportProfile] = [_GENERIC_WIDE]


def load_profiles(user_dir: str | None = None) -> list[ImportProfile]:
    """Return the built-in profiles plus any ``*.json`` profiles in a directory.

    The directory is ``user_dir`` if given, else the ``CAMBER_CONVERT_PROFILES``
    environment variable if set. A profile JSON file is a single object matching
    :meth:`ImportProfile.from_dict`. This is the "drop a file to support a new
    layout" extension point.
    """
    import os

    profiles = list(BUILTIN_PROFILES)
    directory = user_dir or os.environ.get("CAMBER_CONVERT_PROFILES")
    if directory and Path(directory).is_dir():
        for p in sorted(Path(directory).glob("*.json")):
            try:
                profiles.append(ImportProfile.from_dict(json.loads(p.read_text("utf-8"))))
            except (OSError, ValueError, KeyError) as e:  # pragma: no cover - defensive
                raise CsvFormatError(f"invalid profile {p.name}: {e}") from e
    return profiles


def find_profile(name: str, user_dir: str | None = None) -> ImportProfile | None:
    for p in load_profiles(user_dir):
        if p.name == name:
            return p
    return None


def match_profile(fieldnames: list[str],
                  profiles: list[ImportProfile] | None = None) -> ImportProfile | None:
    """Pick the first profile whose ``match_columns`` are all present."""
    present = {norm(f) for f in fieldnames}
    for p in (profiles if profiles is not None else BUILTIN_PROFILES):
        if p.match_columns and all(norm(c) in present for c in p.match_columns):
            return p
    return None


def resolve_channels(profile: ImportProfile, fieldnames: list[str]) -> list[ChannelSpec]:
    """Work out the actual channel columns for this file.

    Explicit ``profile.channels`` come first (in order); then, if a
    ``channel_glob`` is set, any header column matching it that is not already
    covered, not the time column, and not ignored is added with generic defaults.
    """
    ignore = {norm(c) for c in profile.ignore_columns} | {norm(profile.time_column)}
    explicit = {norm(c.column) for c in profile.channels}

    # Keep only explicit channels whose column is actually in the file.
    present = {norm(f): f for f in fieldnames}
    out: list[ChannelSpec] = [c for c in profile.channels if norm(c.column) in present]

    if profile.channel_glob:
        pat = norm(profile.channel_glob)
        for f in fieldnames:
            nf = norm(f)
            if not nf or nf in ignore or nf in explicit:
                continue
            if fnmatch.fnmatch(nf, pat):
                out.append(ChannelSpec(column=f))
    if not out:
        raise CsvFormatError(
            f"profile {profile.name!r} matched no channel columns in header: "
            f"{', '.join(fieldnames)}"
        )
    return out


def build_asset_and_sensors(profile: ImportProfile,
                            channels: list[ChannelSpec]) -> tuple[Asset, list[Sensor]]:
    asset = Asset(id=profile.asset_id, name=profile.asset_name, type=profile.asset_type)
    sensors = [
        Sensor(
            id=c.resolved_id(),
            asset_id=profile.asset_id,
            sensor_type=c.sensor_type,
            unit=c.unit,
            serial_number=None,
            axis=c.axis,
        )
        for c in channels
    ]
    return asset, sensors


def iter_measurements(path: str, profile: ImportProfile,
                      dialect: Dialect | None = None) -> Iterator[Measurement]:
    """Stream :class:`Measurement` objects from a wide CSV, one per valid cell.

    Blank cells and configured ``sentinels`` are skipped. Streaming (rather than
    building a giant list) keeps memory flat on multi-million-row recordings.
    """
    dialect = dialect or sniff_dialect(
        path, delimiter=profile.delimiter, decimal=profile.decimal,
        timestamp_format=profile.timestamp_format,
    )
    sentinels = set(profile.sentinels)
    with open(path, "r", encoding=dialect.encoding, newline="") as fh:
        reader = csv.DictReader(fh, delimiter=dialect.delimiter)
        if reader.fieldnames is None:
            raise CsvFormatError("CSV is empty or has no header row.")
        channels = resolve_channels(profile, list(reader.fieldnames))
        if profile.time_column not in reader.fieldnames:
            raise CsvFormatError(
                f"time column {profile.time_column!r} not in header: "
                f"{', '.join(reader.fieldnames)}"
            )
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            traw = row.get(profile.time_column)
            if traw is None or not traw.strip():
                continue
            try:
                ts = parse_timestamp(traw, dialect.timestamp_format)
            except CsvFormatError as e:
                raise CsvFormatError(f"Row {i}: {e}") from e
            for c in channels:
                val = parse_number(row.get(c.column, ""), dialect.decimal)
                if val is None or val in sentinels:
                    continue
                yield Measurement(
                    timestamp=ts,
                    sensor_id=c.resolved_id(),
                    metric_type=c.resolved_metric(),
                    value=val,
                    unit=c.unit,
                )


def read_wide(path: str, profile: ImportProfile,
              dialect: Dialect | None = None) -> Dataset:
    """Read a wide CSV fully into a :class:`Dataset` (materialised)."""
    dialect = dialect or sniff_dialect(
        path, delimiter=profile.delimiter, decimal=profile.decimal,
        timestamp_format=profile.timestamp_format,
    )
    header = read_header(path, dialect)
    channels = resolve_channels(profile, header)
    asset, sensors = build_asset_and_sensors(profile, channels)
    measurements = list(iter_measurements(path, profile, dialect))
    if not measurements:
        raise CsvFormatError("Wide CSV produced no measurements (all cells empty or sentinel?).")
    return Dataset(
        asset=asset,
        sensors=sensors,
        measurements=measurements,
        source={"reader": "wide_csv", "profile": profile.name,
                "original_file": Path(path).name},
    )
