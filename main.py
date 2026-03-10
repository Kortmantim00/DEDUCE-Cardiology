import sys
from pathlib import Path

# Choose which pipelines should run when the script is executed.
# Set either flag to True and populate the corresponding input lists below.
USE_PDF_PIPELINE = True
USE_CSV_PIPELINE = False

# directory where temporary log files are written (if enabled)
LOGS_DIR = Path("Logs")
LOGS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# simple driver for the PDF pipeline
# ---------------------------------------------------------------------------
if USE_PDF_PIPELINE:
    from deduce_pipeline.pdf import run_pipeline as pdf_run_pipeline

    # list all PDF documents that should be processed
    INPUT_PDFS = [
        Path(r"Input\document1.pdf"),
        # Path(r"Input\document2.pdf"),
        # ...
    ]

    OUTPUT_DIR = Path("Output")
    WRITE_DEDUCE = True   # standard DEDUCE output
    WRITE_CUSTOM = True   # additional custom output
    WRITE_LOGFILE = True  # write warnings to a logfile

    print("\n" + "=" * 60)
    print("DEDUCE PDF PIPELINE")
    print("=" * 60)

    failed = []
    for i, pdf in enumerate(INPUT_PDFS, start=1):
        print(f"\n[{i}/{len(INPUT_PDFS)}] processing: {pdf.name}")
        print("-" * 60)
        try:
            custom_out = OUTPUT_DIR / f"{pdf.stem}_custom.pdf"
            deduce_out = OUTPUT_DIR / f"{pdf.stem}_deduce.pdf"
            pdf_run_pipeline(
                input_pdf=pdf,
                output_custom_pdf=custom_out,
                output_deduce_pdf=deduce_out,
                output_dir=OUTPUT_DIR,
                write_log_file=WRITE_LOGFILE,
                write_custom=WRITE_CUSTOM,
                write_deduce=WRITE_DEDUCE,
                log_dir=LOGS_DIR,
            )
            print(f"✓ {pdf.name} finished successfully\n")
        except Exception as exc:
            print(f"✗ error processing {pdf.name}: {exc}\n", file=sys.stderr)
            failed.append(pdf.name)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Processed: {len(INPUT_PDFS) - len(failed)}/{len(INPUT_PDFS)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("✓ all documents processed successfully")

# ---------------------------------------------------------------------------
# simple driver for the CSV pipeline
# ---------------------------------------------------------------------------
if USE_CSV_PIPELINE:
    from deduce_pipeline.csv import run_pipeline as csv_run_pipeline

    INPUT_CSVS = [
        Path(r"Input\data1.csv"),
        # Path(r"Input\data2.csv"),
    ]

    OUTPUT_DIR = Path("Output")
    WRITE_DEDUCE = True
    WRITE_CUSTOM = True
    WRITE_LOGFILE = True

    print("\n" + "=" * 60)
    print("DEDUCE CSV PIPELINE")
    print("=" * 60)

    failed = []
    for i, csvfile in enumerate(INPUT_CSVS, start=1):
        print(f"\n[{i}/{len(INPUT_CSVS)}] processing: {csvfile.name}")
        print("-" * 60)
        try:
            custom_out = OUTPUT_DIR / f"{csvfile.stem}_custom.pdf"
            deduce_out = OUTPUT_DIR / f"{csvfile.stem}_deduce.pdf"
            csv_run_pipeline(
                input_csv=csvfile,
                output_custom_pdf=custom_out,
                output_deduce_pdf=deduce_out,
                output_dir=OUTPUT_DIR,
                write_log_file=WRITE_LOGFILE,
                write_custom=WRITE_CUSTOM,
                write_deduce=WRITE_DEDUCE,
                log_dir=LOGS_DIR,
            )
            print(f"✓ {csvfile.name} finished successfully\n")
        except Exception as exc:
            print(f"✗ error processing {csvfile.name}: {exc}\n", file=sys.stderr)
            failed.append(csvfile.name)

    print("\n" + "=" * 60)
    print("CSV SUMMARY")
    print("=" * 60)
    print(f"Processed: {len(INPUT_CSVS) - len(failed)}/{len(INPUT_CSVS)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("✓ all CSV files processed successfully")
