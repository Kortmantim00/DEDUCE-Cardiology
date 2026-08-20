"""Command-line interface for the DEDUCE de-identification pipeline.

Usage::

    python -m deduce_pipeline INPUT [INPUT ...] [options]

The input type (PDF, CSV, or TXT) is auto-detected from the file extension.
Run ``python -m deduce_pipeline --help`` for a full option listing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import run_pipeline
from .csv import CsvConfig


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m deduce_pipeline",
        description=(
            "DEDUCE de-identification pipeline. "
            "Input type (PDF/CSV/TXT) is auto-detected from the file extension."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m deduce_pipeline Input/doc.pdf\n"
            "  python -m deduce_pipeline Input/*.pdf --mode custom --format pdf txt\n"
            "  python -m deduce_pipeline Input/*.txt --mode custom --format txt\n"
            "  python -m deduce_pipeline Input/data.csv --format csv\n"
            "  python -m deduce_pipeline Input/data.csv --format pdf json --mode deduce\n"
        ),
    )

    p.add_argument(
        "inputs", nargs="+", type=Path, metavar="INPUT",
        help="One or more input files (.pdf, .csv, or .txt).",
    )
    p.add_argument(
        "--outdir", type=Path, default=Path("Output"), metavar="DIR",
        help="Root output directory (default: Output). A sub-folder per input file is created.",
    )
    p.add_argument(
        "--mode", choices=["deduce", "custom", "both"], default="both",
        help="De-identification mode (default: both).",
    )
    p.add_argument(
        "--format", nargs="+", choices=["pdf", "txt", "json", "csv"],
        default=["pdf"], dest="formats",
        help=(
            "Output format(s) (default: pdf). "
            "Combine freely: --format pdf txt json. "
            "'csv' preserves table structure and is only supported for CSV input."
        ),
    )
    p.add_argument(
        "--no-logfile", action="store_true",
        help="Disable the DEDUCE warning log file.",
    )
    p.add_argument(
        "--log-dir", type=Path, default=Path("Logs"), metavar="DIR",
        help="Directory for log files (default: Logs).",
    )

    csv_grp = p.add_argument_group("CSV options (ignored for PDF input)")
    csv_grp.add_argument(
        "--delimiter", default=",", metavar="CHAR",
        help="CSV field separator (default: ',').",
    )
    csv_grp.add_argument(
        "--encoding", default="utf-8", metavar="ENC",
        help="Input file encoding (default: utf-8).",
    )
    csv_grp.add_argument(
        "--skip-columns", nargs="+", default=[], metavar="COL",
        help="Column names or 0-based indices to pass through unchanged.",
    )
    csv_grp.add_argument(
        "--no-header", action="store_true",
        help="Input CSV has no header row.",
    )
    csv_grp.add_argument(
        "--min-cell-length", type=int, default=2, metavar="N",
        help="Cells shorter than N characters are not de-identified (default: 2).",
    )

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    log_dir: Path | None = None
    if not args.no_logfile:
        args.log_dir.mkdir(parents=True, exist_ok=True)
        log_dir = args.log_dir

    # resolve skip_columns: try to convert numeric strings to int
    skip_cols: list = []
    for col in args.skip_columns:
        try:
            skip_cols.append(int(col))
        except ValueError:
            skip_cols.append(col)

    csv_config = CsvConfig(
        delimiter=args.delimiter,
        encoding=args.encoding,
        has_header=not args.no_header,
        skip_columns=skip_cols,
        min_cell_length=args.min_cell_length,
    )

    total = len(args.inputs)
    failed: list[str] = []

    for i, path in enumerate(args.inputs, 1):
        print(f"\n[{i}/{total}] {path.name}")
        print("-" * 50)
        try:
            run_pipeline(
                input_file=path,
                output_dir=args.outdir,
                mode=args.mode,
                formats=args.formats,
                write_log_file=not args.no_logfile,
                log_dir=log_dir,
                csv_config=csv_config,
            )
            print(f"[OK]")
        except Exception as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            failed.append(path.name)

    print(f"\n{'=' * 50}")
    print(f"Processed: {total - len(failed)}/{total}")
    if failed:
        print(f"Failed:    {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
