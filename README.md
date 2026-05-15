<p align="center">
  <img src="logo.png" alt="Logo" width="320"/>
</p>

# DEDUCE De-identification Pipeline

A Python pipeline for de-identifying Dutch free-text in the domain of cardiology, built on top of the [**DEDUCE**](https://pypi.org/project/deduce) library. Text can be sourced from PDF or CSV files and written to PDF, TXT, JSON, or CSV output. The pipeline is designed for secure, local execution without any external API calls.

## Research context

This pipeline was developed as part of a **clinical AI validation study at Erasmus MC**. The study validates a multi-agent, multi-modal clinical decision support tool based on LLMs and RAG on international cardiology guidelines.

### Two-phase anonymization

| Phase | Method | Goal |
|---|---|---|
| **Phase 1 — Automated** | This pipeline (DEDUCE NER + custom post-processing) | Remove direct and quasi-identifiers |
| **Phase 2 — Manual** | Two independent human reviewers | Verify output; ensure 100% recall |

### Identifier treatment

| Category | Treatment | Examples |
|---|---|---|
| **Direct identifiers** | Fully redacted | Names → `[PERSOON]`, phone → `[TELEFOONNUMMER]` |
| **Quasi-identifiers** | Generalized | Age → `[Leeftijd >=50]`, dates → `[DATUM]`, years → `[JAAR -3]` |
| **Clinical information** | Preserved | Eponymous scores, syndromes, anatomical structures |

---

## Repository structure

```
deduce_pipeline/
    __init__.py       # unified run_pipeline() — auto-detects PDF vs CSV
    __main__.py       # CLI entry point:  python -m deduce_pipeline
    core.py           # shared utilities (DEDUCE init, text helpers, writers)
    pdf.py            # PDF-specific pipeline
    csv.py            # CSV-specific pipeline
main.py               # simple config-driven driver script
tests/
    test_core.py
    test_pipelines.py
requirements.txt
```

---

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
pip install pytest             # optional, for tests
```

---

## Usage

### Option 1 — Command line (recommended)

```bash
python -m deduce_pipeline INPUT [INPUT ...] [options]
```

Input type (PDF or CSV) is **auto-detected from the file extension**.  
Run `python -m deduce_pipeline --help` for the full option listing.

#### Options

| Option | Values | Default | Description |
|---|---|---|---|
| `--mode` | `deduce` \| `custom` \| `both` | `both` | Which de-identification variant(s) to produce |
| `--format` | `pdf` `txt` `json` `csv` | `pdf` | Output format(s); combine freely |
| `--outdir` | path | `Output` | Root output directory |
| `--no-logfile` | flag | — | Disable the DEDUCE warning log |
| `--log-dir` | path | `Logs` | Directory for log files |

**CSV-specific options** (ignored for PDF input):

| Option | Default | Description |
|---|---|---|
| `--delimiter CHAR` | `,` | CSV field separator |
| `--encoding ENC` | `utf-8` | Input file encoding |
| `--skip-columns COL [COL ...]` | — | Column names or 0-based indices to skip |
| `--no-header` | — | File has no header row |
| `--min-cell-length N` | `2` | Cells shorter than N are not de-identified |

### Option 2 — `main.py` driver script

Edit the configuration variables at the top of [main.py](main.py) and run:

```bash
python main.py
```

### Option 3 — Library import

```python
from pathlib import Path
from deduce_pipeline import run_pipeline
from deduce_pipeline.csv import CsvConfig

# PDF input
run_pipeline(Path("Input/document.pdf"), mode="both", formats=["pdf", "txt"])

# CSV input — flat text output
run_pipeline(Path("Input/data.csv"), mode="custom", formats=["pdf", "json"])

# CSV input — preserve table structure
run_pipeline(
    Path("Input/data.csv"),
    formats=["csv"],
    csv_config=CsvConfig(skip_columns=["PatientID"], delimiter=";"),
)
```

---

## Building command strings

This section explains how to compose a command for any use case.

### Template

```
python -m deduce_pipeline <INPUT> --mode <MODE> --format <FORMAT(S)> [--outdir <DIR>] [options]
```

### Step 1 — Choose your input

| Input | Example |
|---|---|
| Single PDF | `Input/document1.pdf` |
| Multiple PDFs | `Input/document1.pdf Input/document2.pdf` |
| All PDFs in a folder | `Input/*.pdf` (shell glob) |
| Single CSV | `Input/data.csv` |

### Step 2 — Choose a mode

| Mode | What is produced |
|---|---|
| `both` | DEDUCE output **and** custom post-processed output (default) |
| `custom` | Custom post-processed output only (recommended for downstream use) |
| `deduce` | Raw DEDUCE output only |

### Step 3 — Choose output format(s)

| Format | Description | CSV input only? |
|---|---|---|
| `pdf` | Formatted PDF document | No |
| `txt` | Plain UTF-8 text file | No |
| `json` | JSON with metadata and section split | No |
| `csv` | Cell-by-cell de-identification, table structure preserved | **Yes** |

Multiple formats can be combined: `--format pdf txt json`

### Step 4 — Add options as needed

| Situation | Add |
|---|---|
| Don't need log files | `--no-logfile` |
| Custom output folder | `--outdir path/to/folder` |
| CSV with semicolons | `--delimiter ";"` |
| Skip ID column | `--skip-columns PatientID` or `--skip-columns 0` |
| CSV without header | `--no-header` |

### Example commands

```bash
# All PDFs in Input/, both modes, PDF output only
python -m deduce_pipeline Input/*.pdf --mode both --format pdf

# Single PDF, custom mode only, all output formats
python -m deduce_pipeline Input/document1.pdf --mode custom --format pdf txt json

# CSV → CSV (cell-by-cell, preserve structure), skip the ID column
python -m deduce_pipeline Input/data.csv --format csv --skip-columns PatientID

# CSV → PDF and JSON (flat-text), deduce mode, semicolon delimiter
python -m deduce_pipeline Input/data.csv --mode deduce --format pdf json --delimiter ";"

# Multiple PDFs, no log file, custom output directory
python -m deduce_pipeline Input/A.pdf Input/B.pdf --mode both --format pdf --outdir Results --no-logfile
```

### Output file naming

Each input file gets its own sub-folder inside `--outdir`:

```
Output/
  document1/
    document1_custom.pdf   ← custom post-processing
    document1_deduce.pdf   ← raw DEDUCE output
    document1_custom.txt
    document1_deduce.json
  data/
    data_custom.csv
    data_deduce.csv
```

---

## Pipeline internals

### 1. Preprocessing

- **Text extraction**: `pdfplumber` (PDF) or row concatenation (CSV flat-text mode)
- **CID code replacement**: `(cid:431)` → `ff`, `(cid:432)` → `ffi`, `(cid:433)` → `ffl`
- **CamelCase splitting**: `drNaamJohannes` → `dr Naam Johannes`

### 2. DEDUCE de-identification

The DEDUCE NER engine detects direct identifiers (names, phone numbers, email addresses, locations). Only warnings are logged; no PHI is written to stdout.

### 3. Custom post-processing (`custom` mode)

Applied on top of DEDUCE output:

| Identifier type | Rule |
|---|---|
| Person names | All persons → `[PERSOON]` |
| Age | Numeric age → `[Leeftijd >=50]` or `[Leeftijd <50]` |
| Full dates (dd-mm-yyyy) | → `[DATUM]` |
| Partial dates (dd/mm, dd-mm) | → `[DATUM]` |
| Years (yyyy) | Newest year → `[JAAR 0]`, earlier → `[JAAR -1]`, `[JAAR -3]`, etc. |
| Dutch month names | → `[MAAND]` |
| Dosages like `3500IE` | Preserved (not treated as locations) |
| Numbered DEDUCE tags (`[X-1]`) | Normalized to `[X]` |

#### Medical terms whitelist

Eponymous terms are preserved to maintain clinical relevance: Glasgow, Barthel, Brugada, Wellens, De Winter, Wells, Sgarbossa, Murphy, circle of Willis, and many more. See `core.get_medical_terms_whitelist()` for the full list.

<p align="center">
  <img src="De-identification flow.png" alt="De-identification flow" width="1000"/>
</p>

---

## Compliance & security

- **No external API calls** — all processing is local
- **Secure cache directory** — DEDUCE cache created with mode `0o700`
- **No PHI in logs** — only DEDUCE warnings are logged
- **HIPAA Safe Harbor** — implements the automated de-identification standard

---

## Testing

```bash
python -m pytest
```

All 32 tests cover core utilities, both pipelines, all output formats, and the CLI.

---

## License

Provided as-is for research and demonstration purposes.
