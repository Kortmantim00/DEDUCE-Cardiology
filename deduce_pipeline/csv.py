"""CSV → DEDUCE → PDF pipeline.

This module exposes a ``run_pipeline`` function and a command‑line entry
point.  The behaviour mirrors :mod:`deduce_pipeline.pdf` but reads from a
CSV file instead of a PDF document.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Tuple

from . import core
import csv


# default paths used by the standalone script
INPUT_CSV: Path = Path("data.csv")
OUTPUT_DIR: Path = Path("output")


def extract_text_from_csv(csv_path: Path) -> str:
    """Read all rows of a CSV and concatenate them into a single string.

    Empty rows are ignored; cells within a row are joined with ``" | "``.
    The resulting lines are joined with ``"\n"``.  This simple format is
    sufficient for the purposes of passing the data to the DEDUCE engine.

    Raises:
        FileNotFoundError: when the file does not exist.
        RuntimeError: if the file contains no usable data.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path.resolve()}")

    lines: list[str] = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                row_text = " | ".join(str(cell).strip() for cell in row if cell.strip())
                if row_text:
                    lines.append(row_text)
    except Exception as exc:
        raise RuntimeError(f"error reading CSV: {exc}") from exc

    combined = "\n".join(lines).strip()
    if not combined:
        raise RuntimeError(f"CSV is empty or contains no usable data: {csv_path}")
    return combined


def run_pipeline(
    input_csv: Path,
    output_custom_pdf: Path | None,
    output_deduce_pdf: Path | None,
    output_dir: Path,
    write_log_file: bool = True,
    write_custom: bool = True,
    write_deduce: bool = True,
    log_dir: Path | None = None,
) -> Tuple[Path | None, Path | None]:
    """Execute the full de‑identification workflow for a CSV file.

    See :func:`core.init_deduce_secure` for details on the logging
    behaviour.  The returned tuple contains the paths of the generated
    PDF files (or ``None`` if that particular output was disabled).
    """
    sd = core.init_deduce_secure(write_log_file=write_log_file, log_dir=log_dir)

    text = extract_text_from_csv(input_csv)
    text = core.fix_cid_codes(text)
    text = core.preprocess_text(text)

    doc = sd.deduce.deidentify(text)
    if hasattr(doc, "annotations"):
        doc.annotations = core.filter_medical_terms(doc.annotations)

    custom_text, _age_category = core.apply_custom_deidentification(doc, text)

    output_dir.mkdir(parents=True, exist_ok=True)

    custom_out: Optional[Path] = None
    deduce_out: Optional[Path] = None

    if write_custom and output_custom_pdf:
        custom_text = core.anonymize_months(custom_text)
        custom_text = core.anonymize_years(custom_text)
        core.write_text_to_pdf(
            custom_text,
            output_custom_pdf,
            title="De‑identified (custom)"
        )
        custom_out = output_custom_pdf

    if write_deduce and output_deduce_pdf:
        core.write_text_to_pdf(
            getattr(doc, "deidentified_text", ""),
            output_deduce_pdf,
            title="De‑identified (DEDUCE)"
        )
        deduce_out = output_deduce_pdf

    # status messages without PHI
    print(f"Input CSV:  {input_csv.resolve()}")
    if custom_out:
        print(f"Output PDF (custom): {custom_out.resolve()}")
    if deduce_out:
        print(f"Output PDF (DEDUCE): {deduce_out.resolve()}")
    if sd.log_file:
        print(f"Log (warnings): {sd.log_file.resolve()}")

    core.close_logging_handlers()
    return custom_out, deduce_out


# -------- command-line interface --------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CSV → DEDUCE → PDF pipeline")
    p.add_argument("--input", type=Path, default=INPUT_CSV, help="input CSV path")
    p.add_argument("--outdir", type=Path, default=OUTPUT_DIR, help="output directory")
    p.add_argument("--custom", type=Path, default=None, help="custom output PDF path (optional)")
    p.add_argument("--deduce", type=Path, default=None, help="DEDUCE output PDF path (optional)")
    p.add_argument("--no-logfile", action="store_true", help="do not write logfile")
    p.add_argument(
        "--output-mode",
        choices=["custom", "deduce", "both"],
        default="both",
        help="which outputs to write",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_csv = args.input
    outdir = args.outdir
    custom_pdf = args.custom if args.custom else (outdir / f"{input_csv.stem}_custom.pdf")
    deduce_pdf = args.deduce if args.deduce else (outdir / f"{input_csv.stem}_deduce.pdf")
    write_custom = args.output_mode in ("custom", "both")
    write_deduce = args.output_mode in ("deduce", "both")
    run_pipeline(
        input_csv=input_csv,
        output_custom_pdf=custom_pdf,
        output_deduce_pdf=deduce_pdf,
        output_dir=outdir,
        write_log_file=not args.no_logfile,
        write_custom=write_custom,
        write_deduce=write_deduce,
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
