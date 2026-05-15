"""CSV → DEDUCE → CSV/PDF/TXT/JSON pipeline.

Two processing strategies are available, selected by the ``formats`` argument:

* **Flat-text** (``formats`` contains ``"pdf"``, ``"txt"``, or ``"json"``):
  all cells are concatenated into one document, de-identified as a block,
  and written to the requested output format(s).

* **Cell-by-cell** (``formats`` contains ``"csv"``):
  each cell is de-identified individually so the original table structure
  (row/column layout, header) is preserved in the output.

Both strategies can be requested in a single call.
"""

from __future__ import annotations

import csv as _csv_module
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from . import core

OUTPUT_DIR: Path = Path("Output")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CsvConfig:
    """Configuration for CSV processing.

    All options have sensible defaults so ``CsvConfig()`` works out-of-the-box
    for a standard comma-delimited UTF-8 file with a header row.

    CSV format
    ----------
    delimiter : str
        Field separator character (``","`` by default; use ``";"`` or
        ``"\\t"`` for other formats).
    encoding : str
        Encoding of the *input* file (e.g. ``"utf-8"``, ``"latin-1"``).
    output_encoding : str
        Encoding used when writing the output CSV.
    has_header : bool
        Set to ``False`` if the file has no header row.
    quoting : int
        A ``csv.QUOTE_*`` constant controlling output quoting style.

    Column selection (cell-by-cell mode only)
    -----------------------------------------
    skip_columns : list[str | int]
        Columns to pass through unchanged.  Each entry may be a column
        *name* (requires ``has_header=True``) or a 0-based column *index*.
    deidentify_header : bool
        When ``True`` the header row itself is run through DEDUCE.

    Cell filtering (cell-by-cell mode only)
    ----------------------------------------
    min_cell_length : int
        Cells shorter than this are passed through unchanged.
    na_values : list[str]
        Cell values treated as missing/empty and passed through unchanged.

    Post-processing (cell-by-cell custom mode)
    -------------------------------------------
    anonymize_months : bool
        Replace Dutch month names with ``[MAAND]``.
    anonymize_years : bool
        Replace 4-digit years with relative placeholders.
    """

    # CSV format
    delimiter: str = ","
    encoding: str = "utf-8"
    output_encoding: str = "utf-8"
    has_header: bool = True
    quoting: int = _csv_module.QUOTE_MINIMAL

    # Column selection
    skip_columns: list = field(default_factory=list)
    deidentify_header: bool = False

    # Cell filtering
    min_cell_length: int = 2
    na_values: list = field(default_factory=lambda: [
        "", "NA", "N/A", "n/a", "NaN", "nan", "NULL", "null", "#N/A",
    ])

    # Post-processing
    anonymize_months: bool = True
    anonymize_years: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_text_from_csv(csv_path: Path, config: Optional[CsvConfig] = None) -> str:
    """Read all rows and concatenate into a single string.

    Rows are joined with newlines; cells within a row with ``" | "``.
    Empty rows and empty cells are ignored.

    Raises:
        FileNotFoundError: When the file does not exist.
        RuntimeError: If the file contains no usable data.
    """
    if config is None:
        config = CsvConfig()
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path.resolve()}")

    lines: list[str] = []
    try:
        with open(csv_path, "r", encoding=config.encoding, newline="") as f:
            reader = _csv_module.reader(f, delimiter=config.delimiter)
            for row in reader:
                if not row:
                    continue
                row_text = " | ".join(str(cell).strip() for cell in row if cell.strip())
                if row_text:
                    lines.append(row_text)
    except Exception as exc:
        raise RuntimeError(f"Error reading CSV '{csv_path}': {exc}") from exc

    combined = "\n".join(lines).strip()
    if not combined:
        raise RuntimeError(f"CSV is empty or contains no usable data: {csv_path}")
    return combined


def _resolve_skip_indices(headers: Optional[list], config: CsvConfig) -> frozenset:
    """Resolve ``config.skip_columns`` to a frozenset of 0-based column indices."""
    indices: set = set()
    for col in config.skip_columns:
        if isinstance(col, int):
            indices.add(col)
        elif isinstance(col, str) and headers is not None:
            try:
                indices.add(headers.index(col))
            except ValueError:
                logging.warning("skip_columns: column %r not found in header — skipped", col)
    return frozenset(indices)


def _deidentify_cell(
    cell: str,
    sd: core.SecureDeduce,
    config: CsvConfig,
    na_set: frozenset,
) -> Tuple[str, str]:
    """De-identify a single cell.  Returns ``(custom_text, deduce_text)``."""
    stripped = cell.strip()
    if not stripped or len(stripped) < config.min_cell_length or stripped in na_set:
        return cell, cell

    try:
        text = core.fix_cid_codes(cell)
        text = core.preprocess_text(text)

        doc = sd.deduce.deidentify(text)
        if hasattr(doc, "annotations"):
            doc.annotations = core.filter_medical_terms(doc.annotations)

        custom_text, _ = core.apply_custom_deidentification(doc, text)
        if config.anonymize_months:
            custom_text = core.anonymize_months(custom_text)
        if config.anonymize_years:
            custom_text = core.anonymize_years(custom_text)

        return custom_text, getattr(doc, "deidentified_text", text)

    except Exception as exc:
        logging.warning("DEDUCE failed on cell (returning original): %s", exc)
        return cell, cell


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    input_csv: Path,
    output_dir: Path = OUTPUT_DIR,
    mode: str = "both",
    formats: list[str] | None = None,
    config: Optional[CsvConfig] = None,
    write_log_file: bool = True,
    log_dir: Optional[Path] = None,
) -> dict[str, Path]:
    """Run the de-identification workflow on a CSV file.

    Args:
        input_csv: Path to the input CSV file.
        output_dir: Root output directory.  A sub-directory named after the
            input stem is created inside it.
        mode: De-identification mode: ``"deduce"``, ``"custom"``, or
            ``"both"`` (default).
        formats: Output format(s) — any subset of
            ``["pdf", "txt", "json", "csv"]``.  Use ``"csv"`` to preserve
            the table structure (cell-by-cell); use ``"pdf"``, ``"txt"``, or
            ``"json"`` to write the full text as a flat document.
            Defaults to ``["pdf"]``.
        config: :class:`CsvConfig` instance.  ``CsvConfig()`` is used when
            ``None``.
        write_log_file: Whether DEDUCE warnings are written to a log file.
        log_dir: Directory for the log file; a temp directory is used when
            ``None``.

    Returns:
        A dict mapping ``"<mode>_<format>"`` keys to the written
        :class:`~pathlib.Path` objects.  Only keys for files that were
        actually written are present.

    Raises:
        FileNotFoundError: If ``input_csv`` does not exist.
        RuntimeError: If the CSV contains no usable data.
    """
    if formats is None:
        formats = ["pdf"]
    if config is None:
        config = CsvConfig()

    input_csv = Path(input_csv)
    if not input_csv.exists():
        raise FileNotFoundError(f"CSV not found: {input_csv.resolve()}")

    write_custom = mode in ("custom", "both")
    write_deduce = mode in ("deduce", "both")

    doc_dir = Path(output_dir) / input_csv.stem
    doc_dir.mkdir(parents=True, exist_ok=True)

    sd = core.init_deduce_secure(write_log_file=write_log_file, log_dir=log_dir)
    written: dict[str, Path] = {}

    # ------------------------------------------------------------------ #
    # Flat-text output: pdf / txt / json                                  #
    # ------------------------------------------------------------------ #
    flat_formats = [f for f in formats if f in ("pdf", "txt", "json")]
    if flat_formats:
        text = extract_text_from_csv(input_csv, config)
        text = core.fix_cid_codes(text)
        text = core.preprocess_text(text)

        doc = sd.deduce.deidentify(text)
        if hasattr(doc, "annotations"):
            doc.annotations = core.filter_medical_terms(doc.annotations)

        if write_deduce:
            deduce_text = getattr(doc, "deidentified_text", "")
            stem = f"{input_csv.stem}_deduce"
            if "pdf" in flat_formats:
                p = doc_dir / f"{stem}.pdf"
                core.write_text_to_pdf(deduce_text, p, "DEDUCE")
                written["deduce_pdf"] = p
            if "txt" in flat_formats:
                p = doc_dir / f"{stem}.txt"
                core.write_text_to_txt(deduce_text, p)
                written["deduce_txt"] = p
            if "json" in flat_formats:
                p = doc_dir / f"{stem}.json"
                admission, plan = core.split_sections(deduce_text)
                core.write_text_to_json(deduce_text, p, input_csv.name, admission, plan)
                written["deduce_json"] = p

        if write_custom:
            custom_text, _ = core.apply_custom_deidentification(doc, text)
            custom_text = core.anonymize_months(custom_text)
            custom_text = core.anonymize_years(custom_text)
            stem = f"{input_csv.stem}_custom"
            if "pdf" in flat_formats:
                p = doc_dir / f"{stem}.pdf"
                core.write_text_to_pdf(custom_text, p, "DEDUCE+CAR")
                written["custom_pdf"] = p
            if "txt" in flat_formats:
                p = doc_dir / f"{stem}.txt"
                core.write_text_to_txt(custom_text, p)
                written["custom_txt"] = p
            if "json" in flat_formats:
                p = doc_dir / f"{stem}.json"
                admission, plan = core.split_sections(custom_text)
                core.write_text_to_json(custom_text, p, input_csv.name, admission, plan)
                written["custom_json"] = p

    # ------------------------------------------------------------------ #
    # Cell-by-cell output: csv                                            #
    # ------------------------------------------------------------------ #
    if "csv" in formats:
        na_set = frozenset(config.na_values)

        try:
            with open(input_csv, "r", encoding=config.encoding, newline="") as f:
                all_rows = list(_csv_module.reader(f, delimiter=config.delimiter))
        except Exception as exc:
            raise RuntimeError(f"Error reading CSV '{input_csv}': {exc}") from exc

        if not all_rows:
            raise RuntimeError(f"CSV is empty: {input_csv}")

        headers: Optional[list] = None
        data_rows = all_rows
        if config.has_header:
            headers = list(all_rows[0])
            data_rows = all_rows[1:]

        skip_indices = _resolve_skip_indices(headers, config)

        proc_header_custom: Optional[list] = headers[:] if headers else None
        proc_header_deduce: Optional[list] = headers[:] if headers else None
        if headers and config.deidentify_header:
            proc_header_custom, proc_header_deduce = [], []
            for i, cell in enumerate(headers):
                if i in skip_indices:
                    proc_header_custom.append(cell)
                    proc_header_deduce.append(cell)
                else:
                    c, d = _deidentify_cell(cell, sd, config, na_set)
                    proc_header_custom.append(c)
                    proc_header_deduce.append(d)

        custom_rows: list = []
        deduce_rows: list = []
        for row in data_rows:
            c_row: list = []
            d_row: list = []
            for col_idx, cell in enumerate(row):
                if col_idx in skip_indices:
                    c_row.append(cell)
                    d_row.append(cell)
                else:
                    c, d = _deidentify_cell(cell, sd, config, na_set)
                    c_row.append(c)
                    d_row.append(d)
            custom_rows.append(c_row)
            deduce_rows.append(d_row)

        def _write_csv_file(path: Path, header: Optional[list], rows: list) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding=config.output_encoding, newline="") as f:
                w = _csv_module.writer(f, delimiter=config.delimiter, quoting=config.quoting)
                if header is not None:
                    w.writerow(header)
                w.writerows(rows)

        if write_custom:
            p = doc_dir / f"{input_csv.stem}_custom.csv"
            _write_csv_file(p, proc_header_custom, custom_rows)
            written["custom_csv"] = p
        if write_deduce:
            p = doc_dir / f"{input_csv.stem}_deduce.csv"
            _write_csv_file(p, proc_header_deduce, deduce_rows)
            written["deduce_csv"] = p

    print(f"Input CSV:  {input_csv.resolve()}")
    print(f"Output dir: {doc_dir.resolve()}")
    if sd.log_file:
        print(f"Log:        {sd.log_file.resolve()}")

    core.close_logging_handlers()
    return written
