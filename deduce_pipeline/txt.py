"""TXT → DEDUCE → PDF/TXT/JSON pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import core

OUTPUT_DIR: Path = Path("Output")


def read_text_from_txt(txt_path: Path) -> str:
    """Read all text from a plain-text file."""
    with open(str(txt_path), encoding="utf-8") as f:
        return f.read()


def run_pipeline(
    input_txt: Path,
    output_dir: Path = OUTPUT_DIR,
    mode: str = "both",
    formats: list[str] | None = None,
    write_log_file: bool = True,
    log_dir: Optional[Path] = None,
) -> dict[str, Path]:
    """Run the de-identification workflow on a TXT file.

    Args:
        input_txt: Path to the input TXT.
        output_dir: Root output directory.  A sub-directory named after the
            subject id is created inside it.
        mode: Which de-identification variant(s) to produce: ``"deduce"``,
            ``"custom"``, or ``"both"`` (default).
        formats: Output format(s) to write — any subset of
            ``["pdf", "txt", "json"]``.  Defaults to ``["pdf"]``.
        write_log_file: Whether DEDUCE warnings are written to a log file.
        log_dir: Directory for the log file; a temp directory is used when
            ``None``.

    Returns:
        A dict mapping ``"<variant>_<format>"`` keys to the written
        :class:`~pathlib.Path` objects (e.g. ``{"deidc_pdf": ...,
        "deidd_txt": ...}``).  Only keys for files that were actually
        written are present.

    Raises:
        FileNotFoundError: If ``input_txt`` does not exist.
        RuntimeError: If the TXT contains no text.
    """
    if formats is None:
        formats = ["pdf"]

    input_txt = Path(input_txt)
    if not input_txt.exists():
        raise FileNotFoundError(f"Input TXT not found: {input_txt.resolve()}")

    write_custom = mode in ("custom", "both")
    write_deduce = mode in ("deduce", "both")

    sd = core.init_deduce_secure(write_log_file=write_log_file, log_dir=log_dir)

    text = read_text_from_txt(input_txt)
    if not text:
        raise RuntimeError("No text extracted from TXT (file is empty).")

    text = core.fix_cid_codes(text)
    text = core.preprocess_text(text)

    doc = sd.deduce.deidentify(text)
    if hasattr(doc, "annotations"):
        doc.annotations = core.filter_medical_terms(doc.annotations)

    # Group output under a subject-level folder (part before _admission/_decision)
    subject_id = core.extract_subject_id(input_txt)
    doc_dir = Path(output_dir) / subject_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    if write_deduce:
        deduce_text = getattr(doc, "deidentified_text", "")
        stem = f"{subject_id}_{input_txt.stem}_deidd"
        if "pdf" in formats:
            p = doc_dir / f"{stem}.pdf"
            core.write_text_to_pdf(deduce_text, p)
            written["deidd_pdf"] = p
        if "txt" in formats:
            p = doc_dir / f"{stem}.txt"
            core.write_text_to_txt(deduce_text, p)
            written["deidd_txt"] = p
        if "json" in formats:
            p = doc_dir / f"{stem}.json"
            admission, plan = core.split_sections(deduce_text)
            core.write_text_to_json(deduce_text, p, input_txt.name, admission, plan)
            written["deidd_json"] = p

    if write_custom:
        custom_text, _ = core.apply_custom_deidentification(doc, text)
        custom_text = core.anonymize_months(custom_text)
        custom_text = core.anonymize_years(custom_text)
        custom_text = core.anonymize_times(custom_text)
        custom_text = core.anonymize_days(custom_text)
        stem = f"{subject_id}_{input_txt.stem}_deidc"
        if "pdf" in formats:
            p = doc_dir / f"{stem}.pdf"
            core.write_text_to_pdf(custom_text, p)
            written["deidc_pdf"] = p
        if "txt" in formats:
            p = doc_dir / f"{stem}.txt"
            core.write_text_to_txt(custom_text, p)
            written["deidc_txt"] = p
        if "json" in formats:
            p = doc_dir / f"{stem}.json"
            admission, plan = core.split_sections(custom_text)
            core.write_text_to_json(custom_text, p, input_txt.name, admission, plan)
            written["deidc_json"] = p

    print(f"Input TXT:  {input_txt.resolve()}")
    print(f"Output dir: {doc_dir.resolve()}")
    if sd.log_file:
        print(f"Log:        {sd.log_file.resolve()}")

    core.close_logging_handlers()
    return written
