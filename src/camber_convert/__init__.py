"""camber-convert: read structural-monitoring data from any format and write
it out in one small open format (JSON metadata + Parquet measurements).

Public API:

    import camber_convert as bc

    dataset = bc.read("recording.csv")          # -> Dataset
    meta_path, data_path = bc.convert(           # read + write in one call
        "recording.csv", out_dir="out/", name="my_bridge"
    )

Low-level writers are available under camber_convert.writers if you want to
write a Dataset you built yourself.
"""

from __future__ import annotations

from pathlib import Path

from .model import (
    FORMAT_NAME,
    FORMAT_VERSION,
    Asset,
    Dataset,
    Location,
    Measurement,
    Sensor,
)
from .readers.base import UnsupportedFormatError, read, supported_extensions
from .writers.json_writer import build_metadata, write_json
from .writers.parquet_writer import write_parquet

# Import reader modules for their @register side effects so read() knows them.
from .readers import csv_reader as _csv_reader  # noqa: F401
from .readers import dewesoft_reader as _dewesoft_reader  # noqa: F401
from .readers import tdms_reader as _tdms_reader  # noqa: F401

__version__ = FORMAT_VERSION

__all__ = [
    "read",
    "convert",
    "write_dataset",
    "supported_extensions",
    "UnsupportedFormatError",
    "Dataset",
    "Asset",
    "Sensor",
    "Measurement",
    "Location",
    "build_metadata",
    "write_json",
    "write_parquet",
    "FORMAT_NAME",
    "FORMAT_VERSION",
    "__version__",
]


def write_dataset(dataset: Dataset, out_dir: str, name: str = "dataset") -> tuple[Path, Path]:
    """Write a Dataset to <out_dir>/<name>.meta.json and <out_dir>/<name>.parquet."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data_name = f"{name}.parquet"
    data_path = write_parquet(dataset, out / data_name)
    meta_path = write_json(dataset, out / f"{name}.meta.json", data_name)
    return meta_path, data_path


def convert(input_path: str, out_dir: str, name: str | None = None) -> tuple[Path, Path]:
    """Read `input_path` and write the open format into `out_dir`.

    Returns (meta_json_path, parquet_path).
    """
    if name is None:
        name = Path(input_path).stem
    dataset = read(input_path)
    return write_dataset(dataset, out_dir, name)
