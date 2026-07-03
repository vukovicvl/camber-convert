# camber-convert

Read structural-monitoring (bridge sensor) data from **any format** and write it
out in **one small, open, documented format** so any tool can use it without
reverse-engineering a proprietary export.

The open format is two files:

| File | Contents |
| --- | --- |
| `<name>.meta.json` | Human-readable metadata: the asset (bridge), its sensors, units, and provenance |
| `<name>.parquet` | The measurements as a compact columnar table |

This library is intentionally small and dependency-light so that other projects
— including [Camber](https://github.com/vukovicvl/camber), web apps, and research
scripts — can adopt it as a shared standard. It is licensed **MIT** for exactly
that reason. **Reading** input files needs only the Python standard library;
**writing** the open-format Parquet file is the optional `[parquet]` extra.

## Install

```bash
pip install camber-convert          # readers + JSON metadata (no heavy deps)
pip install "camber-convert[parquet]"  # + write the open-format .parquet
```

Optional native National Instruments TDMS support:

```bash
pip install "camber-convert[tdms]"
```

## Use it from the command line

```bash
camber-convert recording.csv
camber-convert recording.csv -o converted/ --name danube_bridge
```

## Use it from Python

```python
import camber_convert as bc

# one-shot: read + write the open format
meta_path, data_path = bc.convert("recording.csv", out_dir="out/", name="danube")

# or work with the neutral Dataset directly
dataset = bc.read("recording.csv")
print(dataset.asset.name, len(dataset.sensors), len(dataset.measurements))
```

## Input CSV format

The CSV reader handles two layouts and auto-detects which one a file is. It is
**locale-robust**: the delimiter (`,` / `;` / tab), decimal separator (`.` / `,`),
text encoding (UTF-8 / UTF-8-BOM / UTF-16), and timestamp format are sniffed, so
a file exported in one country reads the same as one from another instead of
silently corrupting.

### Tidy (long) — one reading per row

Column names are case-insensitive and a few common aliases are accepted.

**Required:** `timestamp` (ISO-8601), `sensor_id`, `metric_type`, `value`, `unit`
**Optional:** `asset_id`, `asset_name`, `sensor_type`, `axis`, `serial_number`

```csv
timestamp,sensor_id,metric_type,value,unit,asset_name,axis
2026-01-15T09:30:00Z,ACC-01,acceleration,0.012,m/s^2,Danube Bridge,z
2026-01-15T09:30:01Z,ACC-01,acceleration,0.015,m/s^2,Danube Bridge,z
```

### Wide / multi-channel — one row per timestamp, one column per channel

This is what most data-acquisition systems export. A named **import profile**
describes the layout (which column is the timestamp, which are channels, what
each channel measures, and which value means "no data"); the reader *melts* it
into tidy measurements. Adding support for a new vendor's export is a new profile
(a small JSON file), not new code.

```csv
,ts,id,ch_1,ch_2,...,ch_30,fileid,event
0,2023-02-20T03:10:53,7396779155,444.28,204.03,...,-1000000.0,62018,none
```

```python
import camber_convert as bc

# Inspect a file (shape, dialect, first melted rows) without importing it:
info = bc.inspect_csv("recording.csv", user_dir="profiles/")
# Stream measurements one at a time (millions of rows, flat memory):
for m in bc.stream_measurements("recording.csv", user_dir="profiles/"):
    ...
```

Profiles are loaded from a directory passed as `user_dir=` or from the
`CAMBER_CONVERT_PROFILES` environment variable.

## Parquet schema

| Column | Type |
| --- | --- |
| `timestamp` | `timestamp[ms, UTC]` |
| `sensor_id` | `string` |
| `metric_type` | `string` |
| `value` | `double` |
| `unit` | `string` |

Read it back with pyarrow, pandas, polars, DuckDB, or anything else that speaks
Parquet.

## Supported formats

| Format | Status |
| --- | --- |
| CSV (tidy / long) | ✅ implemented |
| CSV (wide / multi-channel, profile-driven) | ✅ implemented |
| NI TDMS (`.tdms`) | 🚧 stub — implementation plan in `readers/tdms_reader.py` |
| Dewesoft (`.dxd`, `.d7d`) | 🚧 stub — export to CSV for now; see `readers/dewesoft_reader.py` |

Adding a format is a self-contained change: write one module in `readers/`,
decorate it with `@register(".ext")`, and import it in `__init__.py`.

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q
```

## License

MIT — see [LICENSE](LICENSE).
