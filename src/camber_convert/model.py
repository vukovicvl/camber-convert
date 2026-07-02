"""In-memory data model and open-format constants for camber-convert.

The goal of this package is interoperability: read structural-monitoring data
out of any vendor format and write it back out in ONE small, open, documented
format so that any tool (Camber, a web app, a research script, pyOMA2, ...)
can consume it without reverse-engineering a proprietary export.

The open format is two files:

  <name>.meta.json    -- human-readable metadata: the asset (bridge), its
                         sensors, units, and provenance. See json_writer.py.
  <name>.parquet      -- the measurements as a tidy columnar table. See
                         parquet_writer.py.

These dataclasses are the neutral representation in between. Readers produce a
`Dataset`; writers consume one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Bump FORMAT_VERSION on any breaking change to the on-disk shape.
FORMAT_NAME = "camber-open-shm"
FORMAT_VERSION = "0.1.0"


@dataclass
class Location:
    """Optional geographic position of an asset (WGS84)."""

    latitude: float | None = None
    longitude: float | None = None


@dataclass
class Asset:
    """A monitored structure, e.g. a bridge."""

    id: str
    name: str
    type: str = "bridge"
    location: Location | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Sensor:
    """A sensor attached to an asset.

    Mirrors Camber's core Sensor entity so the two line up cleanly.
    `unit` is the physical unit this sensor reports (e.g. "m/s^2", "mm").
    """

    id: str
    asset_id: str
    sensor_type: str
    unit: str
    serial_number: str | None = None
    axis: str | None = None  # e.g. "x", "y", "z" for triaxial sensors


@dataclass
class Measurement:
    """A single reading. `timestamp` should be timezone-aware (UTC preferred)."""

    timestamp: datetime
    sensor_id: str
    metric_type: str
    value: float
    unit: str


@dataclass
class Dataset:
    """Everything a reader extracted from one source file.

    NOTE (performance TODO): `measurements` is a plain list, which is fine for
    small-to-medium files but will use a lot of memory on multi-million-row
    recordings. A future version should let readers stream measurements to the
    Parquet writer in chunks instead of materialising them all at once.
    """

    asset: Asset
    sensors: list[Sensor] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    # Provenance: how this dataset was produced (reader name, original file...).
    source: dict = field(default_factory=dict)
