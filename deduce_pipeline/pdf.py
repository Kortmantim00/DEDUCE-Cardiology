"""PDF → DEDUCE → PDF pipeline.

This module exposes the same public ``run_pipeline`` interface as
:mod:`deduce_pipeline.csv` but works with PDF input.  It uses
``pdfplumber`` to extract the text before passing it to the core logic.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Tuple

from . import core
import pdfplumber

# default paths for the standalone script
INPUT_PDF: Path = Path("document1.pdf")
OUTPUT_DIR: Path = Path("output")


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all readable text from a PDF using :mod:`pdfplumber`.

    Pages are separated by double newlines in the returned string.  If
    the document contains no text, an empty string is returned.
    """
    text_parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
    return "\n\n".join(text_parts).strip()


def run_pipeline(
    input_pdf: Path,
    output_custom_pdf: Path | None,
    output_deduce_pdf: Path | None,
    output_dir: Path,
    write_log_file: bool = True,
    write_custom: bool = True,
    write_deduce: bool = True,
    log_dir: Path | None = None,
) -> Tuple[Path | None, Path | None]:
    """Run the de‑identification workflow on a PDF file.

    The semantics are identical to :func:`deduce_pipeline.csv.run_pipeline`.
    """
    sd = core.init_deduce_secure(write_log_file=write_log_file, log_dir=log_dir)

    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf.resolve()}")

    text = extract_text_from_pdf(input_pdf)
    if not text:
        raise RuntimeError("no text extracted from PDF (empty or non‑textual)")

    text = core.fix_cid_codes(text)
    text = core.preprocess_text(text)

    doc = sd.deduce.deidentify(text)
    if hasattr(doc, "annotations"):
        doc.annotations = core.filter_medical_terms(doc.annotations)

    output_dir.mkdir(parents=True, exist_ok=True)

    custom_out: Optional[Path] = None
    deduce_out: Optional[Path] = None

    if write_deduce and output_deduce_pdf:
        core.write_text_to_pdf(
            getattr(doc, "deidentified_text", ""),
            output_deduce_pdf,
            title="De‑identified (DEDUCE)"
        )
        deduce_out = output_deduce_pdf

    if write_custom and output_custom_pdf:
        custom_text, _age_category = core.apply_custom_deidentification(doc, text)
        custom_text = core.anonymize_months(custom_text)
        custom_text = core.anonymize_years(custom_text)
        core.write_text_to_pdf(
            custom_text,
            output_custom_pdf,
            title="De‑identified (custom)"
        )
        custom_out = output_custom_pdf

    print(f"Input PDF:  {input_pdf.resolve()}")
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
    p = argparse.ArgumentParser(description="PDF → DEDUCE → PDF pipeline")
    p.add_argument("--input", type=Path, default=INPUT_PDF, help="input PDF path")
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
    input_pdf = args.input
    outdir = args.outdir
    custom_pdf = args.custom if args.custom else (outdir / f"{input_pdf.stem}_deidentified_custom.pdf")
    deduce_pdf = args.deduce if args.deduce else (outdir / f"{input_pdf.stem}_deidentified_deduce.pdf")
    write_custom = args.output_mode in ("custom", "both")
    write_deduce = args.output_mode in ("deduce", "both")
    run_pipeline(
        input_pdf=input_pdf,
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
