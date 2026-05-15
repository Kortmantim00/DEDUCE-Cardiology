"""Configuration-driven driver script.

Edit the variables in the CONFIGURE section below, then run:

    python main.py

For a full-featured command-line interface, use instead:

    python -m deduce_pipeline --help
"""

import sys
from pathlib import Path

from deduce_pipeline import run_pipeline
from deduce_pipeline.csv import CsvConfig

# -----------------------------------------------------------------------
# CONFIGURE
# -----------------------------------------------------------------------

INPUTS = [
    Path("Input/document1.pdf"),
    # Path("Input/document2.pdf"),
    # Path("Input/data.csv"),
]

OUTPUT_DIR    = Path("Output")
LOG_DIR       = Path("Logs")
MODE          = "both"       # "deduce" | "custom" | "both"
FORMATS       = ["pdf"]      # any of: "pdf", "txt", "json", "csv"
                             # "csv" only applies to CSV input (preserves structure)
WRITE_LOGFILE = True

# CSV-specific settings — ignored when processing PDF files
CSV_CONFIG = CsvConfig(
    delimiter=",",
    encoding="utf-8",
    has_header=True,
    skip_columns=[],         # e.g. ["PatientID"] or [0]
)

# -----------------------------------------------------------------------
# RUN  (no changes needed below this line)
# -----------------------------------------------------------------------

LOG_DIR.mkdir(exist_ok=True)

print("=" * 60)
print("DEDUCE PIPELINE")
print("=" * 60)

failed: list[str] = []

for i, path in enumerate(INPUTS, 1):
    print(f"\n[{i}/{len(INPUTS)}] {path.name}")
    print("-" * 60)
    try:
        run_pipeline(
            input_file=path,
            output_dir=OUTPUT_DIR,
            mode=MODE,
            formats=FORMATS,
            write_log_file=WRITE_LOGFILE,
            log_dir=LOG_DIR,
            csv_config=CSV_CONFIG,
        )
        print(f"[OK] {path.name}")
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        failed.append(path.name)

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Processed: {len(INPUTS) - len(failed)}/{len(INPUTS)}")
if failed:
    print(f"Failed:    {', '.join(failed)}", file=sys.stderr)
    sys.exit(1)
else:
    print("[OK] all files processed successfully")
