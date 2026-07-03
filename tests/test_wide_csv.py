"""Tests for the wide / multi-channel CSV reader and locale robustness."""

from __future__ import annotations

import json

import camber_convert as bc
from camber_convert import ChannelSpec, ImportProfile

# A small file shaped like a real DAQ export: unnamed index, ts, a row id, N
# channel columns, a constant file id, and an event flag. ch_3 is always the
# no-data sentinel.
WIDE_CSV = """,ts,id,ch_1,ch_2,ch_3,fileid,event
0,2023-02-20T03:10:53,7396779155,444.28,204.03,-1000000.0,62018,none
1,2023-02-20T03:10:53.005000,7396779156,444.02,203.84,-1000000.0,62018,none
"""

ACME = ImportProfile(
    name="acme",
    match_columns=["ts", "id", "ch_1"],
    time_column="ts",
    ignore_columns=["", "id", "fileid", "event"],
    channel_glob="ch_*",
    channels=[ChannelSpec(column="ch_1", sensor_id="ACC-X", sensor_type="accelerometer",
                          metric_type="acceleration", unit="g", axis="x")],
    sentinels=[-1000000.0],
    asset_id="bridge-1", asset_name="Test Bridge",
)


def test_wide_melt_and_sentinel(tmp_path):
    src = tmp_path / "rec.csv"
    src.write_text(WIDE_CSV, encoding="utf-8")

    ds = bc.read_csv(str(src), profile=ACME)

    # 3 channels discovered (ch_1 explicit, ch_2/ch_3 generic), 3 sensors.
    assert {s.id for s in ds.sensors} == {"ACC-X", "ch_2", "ch_3"}
    # ch_3 is all sentinel -> no measurements; ch_1 + ch_2 over 2 rows = 4.
    assert len(ds.measurements) == 4
    assert all(m.value != -1000000.0 for m in ds.measurements)

    accx = [m for m in ds.measurements if m.sensor_id == "ACC-X"]
    assert accx[0].value == 444.28
    assert accx[0].metric_type == "acceleration"
    assert accx[0].unit == "g"
    # a generically-mapped channel gets column name as metric_type, empty unit
    ch2 = [m for m in ds.measurements if m.sensor_id == "ch_2"]
    assert ch2[0].metric_type == "ch_2" and ch2[0].unit == ""


def test_inspect_preview(tmp_path):
    src = tmp_path / "rec.csv"
    src.write_text(WIDE_CSV, encoding="utf-8")

    info = bc.inspect_csv(str(src), profile=ACME, sample=3)
    assert info.kind == "wide"
    assert info.profile_name == "acme"
    assert info.asset.name == "Test Bridge"
    assert len(info.preview) == 3


EU_CSV = (
    "ts;ch_1;ch_2\r\n"
    "20.02.2023 03:10:53;444,28;204,03\r\n"
    "20.02.2023 03:10:54;445,00;-1000000,0\r\n"
)

EU_PROFILE = ImportProfile(
    name="eu",
    match_columns=["ts", "ch_1"],
    time_column="ts",
    channel_glob="ch_*",
    sentinels=[-1000000.0],
    asset_name="EU Bridge",
)


def test_eu_locale_semicolon_and_decimal_comma(tmp_path):
    src = tmp_path / "eu.csv"
    src.write_text(EU_CSV, encoding="utf-8")

    info = bc.inspect_csv(str(src), profile=EU_PROFILE)
    assert info.dialect.delimiter == ";"
    assert info.dialect.decimal == ","
    assert any("Decimal comma" in w for w in info.warnings)

    ds = bc.read_csv(str(src), profile=EU_PROFILE)
    values = sorted(m.value for m in ds.measurements)
    # 444.28, 445.00, 204.03 -> the -1000000 sentinel is dropped
    assert values == [204.03, 444.28, 445.0]


def test_json_profile_autodetect(tmp_path):
    src = tmp_path / "rec.csv"
    src.write_text(WIDE_CSV, encoding="utf-8")
    prof_dir = tmp_path / "profiles"
    prof_dir.mkdir()
    (prof_dir / "acme.json").write_text(json.dumps({
        "name": "acme-json",
        "match_columns": ["ts", "id", "ch_1"],
        "time_column": "ts",
        "ignore_columns": ["", "id", "fileid", "event"],
        "channel_glob": "ch_*",
        "sentinels": [-1000000.0],
        "asset_name": "JSON Bridge",
    }), encoding="utf-8")

    # No explicit profile: auto-match against the dropped-in JSON profile.
    info = bc.inspect_csv(str(src), user_dir=str(prof_dir))
    assert info.kind == "wide"
    assert info.profile_name == "acme-json"
    ds = bc.read_csv(str(src), user_dir=str(prof_dir))
    assert len(ds.measurements) == 4


def test_streaming_matches_materialised(tmp_path):
    src = tmp_path / "rec.csv"
    src.write_text(WIDE_CSV, encoding="utf-8")
    streamed = list(bc.stream_measurements(str(src), profile=ACME))
    materialised = bc.read_csv(str(src), profile=ACME).measurements
    assert len(streamed) == len(materialised) == 4


TIDY_CSV = """timestamp,sensor_id,metric_type,value,unit
2026-01-15T09:30:00Z,ACC-01,acceleration,0.012,m/s^2
2026-01-15T09:30:01Z,ACC-01,acceleration,0.015,m/s^2
"""


def test_tidy_still_reads_as_tidy(tmp_path):
    src = tmp_path / "tidy.csv"
    src.write_text(TIDY_CSV, encoding="utf-8")
    info = bc.inspect_csv(str(src))
    assert info.kind == "tidy"
    assert {s.id for s in info.sensors} == {"ACC-01"}
