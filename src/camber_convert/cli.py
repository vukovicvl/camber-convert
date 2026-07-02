"""Command-line interface: convert one file to the open format.

Usage:
    camber-convert INPUT [-o OUT_DIR] [--name NAME]
    python -m camber_convert INPUT [-o OUT_DIR] [--name NAME]

Examples:
    camber-convert recording.csv
    camber-convert recording.csv -o converted/ --name novi_sad_bridge
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, convert, supported_extensions
from .readers.base import UnsupportedFormatError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="camber-convert",
        description="Convert structural-monitoring data to the Camber open format "
        "(JSON metadata + Parquet measurements).",
    )
    p.add_argument("input", help="Input file to convert (e.g. recording.csv)")
    p.add_argument(
        "-o",
        "--out-dir",
        default=".",
        help="Directory to write the output files into (default: current dir)",
    )
    p.add_argument(
        "--name",
        default=None,
        help="Base name for the output files (default: input file stem)",
    )
    p.add_argument("--version", action="version", version=f"camber-convert {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not Path(args.input).is_file():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    try:
        meta_path, data_path = convert(args.input, args.out_dir, args.name)
    except UnsupportedFormatError as e:
        print(f"error: {e}", file=sys.stderr)
        print(f"supported formats: {', '.join(supported_extensions())}", file=sys.stderr)
        return 2
    except NotImplementedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # readers raise their own *FormatError types
        print(f"error: could not convert '{args.input}': {e}", file=sys.stderr)
        return 1

    print("Converted successfully:")
    print(f"  metadata : {meta_path}")
    print(f"  data     : {data_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
