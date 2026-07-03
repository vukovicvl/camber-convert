"""Locale-robust CSV parsing helpers shared by the tidy and wide CSV readers.

The problem these solve: a CSV exported on one machine is not the same as a CSV
exported on another. Delimiters (``,`` vs ``;`` vs tab), decimal separators
(``.`` vs ``,``), text encodings (UTF-8, UTF-8-with-BOM, UTF-16), and timestamp
formats all vary by locale and by the tool that wrote the file. A reader that
assumes one shape silently corrupts or rejects the others.

Nothing here is format-specific; it is pure, dependency-free text handling so it
stays usable from any reader in this package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Delimiters we are willing to auto-detect, most-specific first.
_CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]

# Strings that mean "no reading" regardless of locale.
_NULL_TOKENS = {"", "nan", "na", "n/a", "null", "none", "-", "--"}

# Timestamp formats tried after ISO-8601. ISO is handled by fromisoformat();
# these cover the common European / US spreadsheet exports. Note that slash
# dates are genuinely ambiguous (DD/MM vs MM/DD) and cannot be resolved by
# sniffing -- a profile should pin `timestamp_format` when they occur.
_FALLBACK_TS_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%d.%m.%Y %H:%M:%S.%f",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
    "%d/%m/%Y %H:%M:%S",
]


class CsvFormatError(Exception):
    """Raised when a CSV cannot be parsed (bad header, values, or encoding)."""


@dataclass
class Dialect:
    """How to decode and split a particular CSV file."""

    encoding: str = "utf-8-sig"
    delimiter: str = ","
    decimal: str = "."  # "." or ","
    # timestamp_format is None => auto (ISO first, then the fallbacks above).
    timestamp_format: str | None = None


def norm(name: str) -> str:
    """Canonical form of a header cell for matching (case/space/BOM-insensitive)."""
    return (name or "").strip().lstrip("﻿").lower()


def detect_encoding(path: str) -> str:
    """Pick a text encoding from the file's leading bytes (BOM sniffing)."""
    with open(path, "rb") as fh:
        head = fh.read(4)
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16"
    # No BOM: prefer strict UTF-8, fall back to latin-1 (never raises) if needed.
    try:
        with open(path, "r", encoding="utf-8") as fh:
            fh.read(4096)
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _detect_delimiter(header_line: str) -> str:
    """Choose the delimiter that best splits the header line."""
    counts = {d: header_line.count(d) for d in _CANDIDATE_DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def sniff_dialect(path: str, *, delimiter: str | None = None,
                  decimal: str | None = None,
                  timestamp_format: str | None = None) -> Dialect:
    """Infer a :class:`Dialect` for ``path``.

    Any of ``delimiter`` / ``decimal`` / ``timestamp_format`` passed explicitly
    (e.g. from an import profile) overrides the auto-detection for that field.
    """
    encoding = detect_encoding(path)
    with open(path, "r", encoding=encoding, newline="") as fh:
        header_line = fh.readline()

    delim = delimiter or _detect_delimiter(header_line)
    if decimal:
        dec = decimal
    else:
        # A semicolon delimiter almost always implies a decimal comma (the whole
        # reason ';' is used is that ',' is taken by the decimal separator).
        dec = "," if delim == ";" else "."
    return Dialect(encoding=encoding, delimiter=delim, decimal=dec,
                   timestamp_format=timestamp_format)


def parse_number(raw: str, decimal: str = ".") -> float | None:
    """Parse a locale-formatted number. Returns None for null-ish tokens.

    With ``decimal=','`` the comma is the decimal point and ``.`` is treated as a
    thousands separator; with ``decimal='.'`` the reverse.
    """
    s = (raw or "").strip()
    if s.lower() in _NULL_TOKENS:
        return None
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")  # strip thousands separators
    try:
        return float(s)
    except ValueError:
        return None


def parse_timestamp(raw: str, fmt: str | None = None) -> datetime:
    """Parse a timestamp into a timezone-aware UTC datetime.

    Tries ``fmt`` first if given, then ISO-8601 (accepting a trailing ``Z``),
    then a list of common spreadsheet formats. Naive results are assumed UTC.
    """
    s = (raw or "").strip()
    if not s:
        raise CsvFormatError("empty timestamp")

    dt: datetime | None = None
    if fmt:
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError as e:
            raise CsvFormatError(f"timestamp {s!r} does not match format {fmt!r}") from e
    else:
        iso = s[:-1] + "+00:00" if s.endswith("Z") else s
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            for candidate in _FALLBACK_TS_FORMATS:
                try:
                    dt = datetime.strptime(s, candidate)
                    break
                except ValueError:
                    continue
        if dt is None:
            raise CsvFormatError(f"unrecognised timestamp format: {s!r}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def read_header(path: str, dialect: Dialect) -> list[str]:
    """Return the raw header cells of a CSV using the given dialect."""
    import csv

    with open(path, "r", encoding=dialect.encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter=dialect.delimiter)
        for row in reader:
            return list(row)
    raise CsvFormatError(f"{Path(path).name} is empty or has no header row.")
