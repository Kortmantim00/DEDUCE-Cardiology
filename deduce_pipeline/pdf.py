"""PDF → DEDUCE → PDF/TXT/JSON pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pdfplumber
from . import core

OUTPUT_DIR: Path = Path("Output")


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all readable text from a PDF using pdfplumber.

    Pages are separated by double newlines.  Returns an empty string when
    no text can be extracted.
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
    output_dir: Path = OUTPUT_DIR,
    mode: str = "both",
    formats: list[str] | None = None,
    write_log_file: bool = True,
    log_dir: Optional[Path] = None,
) -> dict[str, Path]:
    """Run the de-identification workflow on a PDF file.

    Args:
        input_pdf: Path to the input PDF.
        output_dir: Root output directory.  A sub-directory named after the
            input stem is created inside it.
        mode: Which de-identification variant(s) to produce: ``"deduce"``,
            ``"custom"``, or ``"both"`` (default).
        formats: Output format(s) to write — any subset of
            ``["pdf", "txt", "json"]``.  Defaults to ``["pdf"]``.
        write_log_file: Whether DEDUCE warnings are written to a log file.
        log_dir: Directory for the log file; a temp directory is used when
            ``None``.

    Returns:
        A dict mapping ``"<mode>_<format>"`` keys to the written
        :class:`~pathlib.Path` objects (e.g. ``{"custom_pdf": ...,
        "deduce_txt": ...}``).  Only keys for files that were actually
        written are present.

    Raises:
        FileNotFoundError: If ``input_pdf`` does not exist.
        RuntimeError: If no text could be extracted from the PDF.
    """
    if formats is None:
        formats = ["pdf"]

    input_pdf = Path(input_pdf)
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf.resolve()}")

    write_custom = mode in ("custom", "both")
    write_deduce = mode in ("deduce", "both")

    sd = core.init_deduce_secure(write_log_file=write_log_file, log_dir=log_dir)

    text = extract_text_from_pdf(input_pdf)
    if not text:
        raise RuntimeError("No text extracted from PDF (empty or non-textual).")

    text = core.fix_cid_codes(text)
    text = core.preprocess_text(text)

    doc = sd.deduce.deidentify(text)
    if hasattr(doc, "annotations"):
        doc.annotations = core.filter_medical_terms(doc.annotations)

    doc_dir = Path(output_dir) / input_pdf.stem
    doc_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    if write_deduce:
        deduce_text = getattr(doc, "deidentified_text", "")
        stem = f"{input_pdf.stem}_deduce"
        if "pdf" in formats:
            p = doc_dir / f"{stem}.pdf"
            core.write_text_to_pdf(deduce_text, p, "DEDUCE")
            written["deduce_pdf"] = p
        if "txt" in formats:
            p = doc_dir / f"{stem}.txt"
            core.write_text_to_txt(deduce_text, p)
            written["deduce_txt"] = p
        if "json" in formats:
            p = doc_dir / f"{stem}.json"
            admission, plan = core.split_sections(deduce_text)
            core.write_text_to_json(deduce_text, p, input_pdf.name, admission, plan)
            written["deduce_json"] = p

    if write_custom:
        custom_text, _ = core.apply_custom_deidentification(doc, text)
        custom_text = core.anonymize_months(custom_text)
        custom_text = core.anonymize_years(custom_text)
        stem = f"{input_pdf.stem}_custom"
        if "pdf" in formats:
            p = doc_dir / f"{stem}.pdf"
            core.write_text_to_pdf(custom_text, p, "DEDUCE+CAR")
            written["custom_pdf"] = p
        if "txt" in formats:
            p = doc_dir / f"{stem}.txt"
            core.write_text_to_txt(custom_text, p)
            written["custom_txt"] = p
        if "json" in formats:
            p = doc_dir / f"{stem}.json"
            admission, plan = core.split_sections(custom_text)
            core.write_text_to_json(custom_text, p, input_pdf.name, admission, plan)
            written["custom_json"] = p

    print(f"Input PDF:  {input_pdf.resolve()}")
    print(f"Output dir: {doc_dir.resolve()}")
    if sd.log_file:
        print(f"Log:        {sd.log_file.resolve()}")

    core.close_logging_handlers()
    return written
