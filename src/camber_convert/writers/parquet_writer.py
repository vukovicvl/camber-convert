"""Writes the measurements half of the open format: <name>.parquet.

Tidy/long schema, one row per reading:

    timestamp    timestamp[ms, UTC]
    sensor_id    string
    metric_type  string
    value        double
    unit         string

We use pyarrow directly (not pandas) to keep the dependency footprint small --
important for a library other tools are meant to adopt. Parquet is compact and
fast to read back with pyarrow, pandas, polars, DuckDB, etc.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..model import Dataset

SCHEMA = pa.schema(
    [
        pa.field("timestamp", pa.timestamp("ms", tz="UTC")),
        pa.field("sensor_id", pa.string()),
        pa.field("metric_type", pa.string()),
        pa.field("value", pa.float64()),
        pa.field("unit", pa.string()),
    ]
)


def _to_table(dataset: Dataset) -> pa.Table:
    ms = dataset.measurements
    return pa.table(
        {
            "timestamp": pa.array([m.timestamp for m in ms], type=SCHEMA.field("timestamp").type),
            "sensor_id": [m.sensor_id for m in ms],
            "metric_type": [m.metric_type for m in ms],
            "value": [m.value for m in ms],
            "unit": [m.unit for m in ms],
        },
        schema=SCHEMA,
    )


def write_parquet(dataset: Dataset, path: str) -> Path:
    """Write measurements to a Parquet file at `path`. Returns the path."""
    table = _to_table(dataset)
    p = Path(path)
    pq.write_table(table, p, compression="snappy")
    return p
