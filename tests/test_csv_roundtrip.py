"""Round-trip test: write a small CSV, convert it, read the outputs back."""

from __future__ import annotations

import json

import pyarrow.parquet as pq

import camber_convert as bc

SAMPLE_CSV = """timestamp,sensor_id,metric_type,value,unit,asset_name,axis
2026-01-15T09:30:00Z,ACC-01,acceleration,0.012,m/s^2,Danube Bridge,z
2026-01-15T09:30:01Z,ACC-01,acceleration,0.015,m/s^2,Danube Bridge,z
2026-01-15T09:30:00Z,DISP-01,displacement,2.3,mm,Danube Bridge,
2026-01-15T09:30:01Z,DISP-01,displacement,2.4,mm,Danube Bridge,
"""


def test_convert_csv(tmp_path):
    src = tmp_path / "recording.csv"
    src.write_text(SAMPLE_CSV, encoding="utf-8")

    meta_path, data_path = bc.convert(str(src), str(tmp_path / "out"), name="danube")

    assert meta_path.exists()
    assert data_path.exists()
    assert meta_path.name == "danube.meta.json"
    assert data_path.name == "danube.parquet"

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["format"] == "camber-open-shm"
    assert meta["asset"]["name"] == "Danube Bridge"
    assert meta["measurement_count"] == 4
    assert {s["id"] for s in meta["sensors"]} == {"ACC-01", "DISP-01"}
    assert meta["measurements_file"] == "danube.parquet"

    table = pq.read_table(data_path)
    assert table.num_rows == 4
    assert table.column_names == ["timestamp", "sensor_id", "metric_type", "value", "unit"]
    # values preserved
    assert set(table.column("sensor_id").to_pylist()) == {"ACC-01", "DISP-01"}


def test_unsupported_extension(tmp_path):
    bad = tmp_path / "recording.xyz"
    bad.write_text("nope", encoding="utf-8")
    try:
        bc.read(str(bad))
    except bc.UnsupportedFormatError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected UnsupportedFormatError")
