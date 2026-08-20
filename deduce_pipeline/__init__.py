"""DEDUCE de-identification pipeline.

Public API — import :func:`run_pipeline` for a unified interface that
auto-detects the input type from the file extension:

* ``.pdf`` → :func:`deduce_pipeline.pdf.run_pipeline`
* ``.csv`` → :func:`deduce_pipeline.csv.run_pipeline`
* ``.txt`` → :func:`deduce_pipeline.txt.run_pipeline`

Example::

    from pathlib import Path
    from deduce_pipeline import run_pipeline

    run_pipeline(Path("Input/document.pdf"), output_dir=Path("Output"))
    run_pipeline(Path("Input/data.csv"), formats=["csv"], mode="custom")
    run_pipeline(Path("Input/document.txt"), output_dir=Path("Output"))
"""

from __future__ import annotations

from pathlib import Path


def run_pipeline(
    input_file,
    output_dir: Path = Path("Output"),
    mode: str = "both",
    formats: list[str] | None = None,
    *,
    write_log_file: bool = True,
    log_dir=None,
    csv_config=None,
) -> dict:
    """Unified pipeline that auto-detects the input type from the file extension.

    Args:
        input_file: Path to a PDF, CSV, or TXT file.
        output_dir: Root output directory.  A sub-directory named after the
            input stem is created inside it.
        mode: De-identification mode: ``"deduce"``, ``"custom"``, or
            ``"both"`` (default).
        formats: Output format(s): any subset of ``["pdf", "txt", "json", "csv"]``.
            ``"csv"`` is only supported for CSV input.  Defaults to ``["pdf"]``.
        write_log_file: Whether DEDUCE warnings are written to a log file.
        log_dir: Directory for the log file; a temp directory is used when
            ``None``.
        csv_config: A :class:`~deduce_pipeline.csv.CsvConfig` instance
            (CSV input only).

    Returns:
        A dict mapping ``"<variant>_<format>"`` keys to the written
        :class:`~pathlib.Path` objects, e.g.
        ``{"deidc_pdf": ..., "deidd_txt": ...}``.
        ``deidc`` = custom (DEDUCE + CAR) variant; ``deidd`` = DEDUCE-only variant.

    Raises:
        FileNotFoundError: If the input file does not exist.
        RuntimeError: If the file contains no processable content.
    """
    p = Path(input_file)
    if p.suffix.lower() == ".csv":
        from .csv import run_pipeline as _run
        return _run(
            input_csv=p,
            output_dir=Path(output_dir),
            mode=mode,
            formats=formats,
            config=csv_config,
            write_log_file=write_log_file,
            log_dir=log_dir,
        )
    elif p.suffix.lower() == ".txt":
        from .txt import run_pipeline as _run
        return _run(
            input_txt=p,
            output_dir=Path(output_dir),
            mode=mode,
            formats=formats,
            write_log_file=write_log_file,
            log_dir=log_dir,
        )
    else:
        from .pdf import run_pipeline as _run
        return _run(
            input_pdf=p,
            output_dir=Path(output_dir),
            mode=mode,
            formats=formats,
            write_log_file=write_log_file,
            log_dir=log_dir,
        )
