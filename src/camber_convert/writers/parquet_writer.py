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

pyarrow is imported lazily (and is an optional ``[parquet]`` extra) so that the
*readers* -- which need no pyarrow -- can be used on their own, including on
Python builds that do not yet have a pyarrow wheel. Only writing Parquet
requires it.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Dataset


def _require_pyarrow():
    try:
        import pyarrow as pa  # noqa: F401
        import pyarrow.parquet as pq  # noqa: F401
    except ModuleNotFoundError as e:  # pragma: no cover - environment-dependent
        raise ModuleNotFoundError(
            "Writing the open-format Parquet file requires pyarrow. Install the "
            "optional extra:  pip install \"camber-convert[parquet]\"  "
            "(reading input files does not need pyarrow)."
        ) from e
    return pa, pq


def _schema(pa):
    return pa.schema(
        [
            pa.field("timestamp", pa.timestamp("ms", tz="UTC")),
            pa.field("sensor_id", pa.string()),
            pa.field("metric_type", pa.string()),
            pa.field("value", pa.float64()),
            pa.field("unit", pa.string()),
        ]
    )


def _to_table(dataset: Dataset, pa):
    ms = dataset.measurements
    schema = _schema(pa)
    return pa.table(
        {
            "timestamp": pa.array([m.timestamp for m in ms], type=schema.field("timestamp").type),
            "sensor_id": [m.sensor_id for m in ms],
            "metric_type": [m.metric_type for m in ms],
            "value": [m.value for m in ms],
            "unit": [m.unit for m in ms],
        },
        schema=schema,
    )


def write_parquet(dataset: Dataset, path: str) -> Path:
    """Write measurements to a Parquet file at `path`. Returns the path.

    Requires the optional ``pyarrow`` dependency (``camber-convert[parquet]``).
    """
    pa, pq = _require_pyarrow()
    table = _to_table(dataset, pa)
    p = Path(path)
    pq.write_table(table, p, compression="snappy")
    return p
