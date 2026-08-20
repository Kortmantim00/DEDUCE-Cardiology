<p align="center">
  <img src="media/logo.png" alt="Logo" width="320"/>
</p>

# DEDUCE De-identification Pipeline

A Python pipeline for de-identifying Dutch free-text in the domain of cardiology, built on top of the [**DEDUCE**](https://pypi.org/project/deduce) library. Text can be sourced from PDF, CSV, or TXT files and written to PDF, TXT, JSON, or CSV output. The pipeline is designed for secure, local execution without any external API calls.

## Research context

This pipeline was developed as part of a **clinical AI validation study at Erasmus MC**. The study validates a multi-agent, multi-modal clinical decision support tool based on LLMs and RAG on international cardiology guidelines.

### Two-step de-identification

| Step | Description |
|---|---|
| **1 Original DEDUCE** | Utilizing the NER tool called DEDUCE for de-identification developed bij the UMCU (https://github.com/vmenger/deduce) |
| **2 Custom post-processing** | Applied some custom improvements and adjustments for the cardiology domain. | 

### Identifier treatment

| Category | Treatment | Examples |
|---|---|---|
| **Direct identifiers** | Fully redacted | Names → `[PERSOON]`, phone → `[TELEFOONNUMMER]` |
| **Quasi-identifiers** | Generalized | Age → `[LEEFTIJD 50-65]`, dates → `[DATUM]`, years → `[JAAR -3]`, times → `[TIJD]`, weekdays → `[DAG]` |
| **Clinical information** | Preserved | Eponymous scores, syndromes, anatomical structures |

### Data types
| Input | Output |
|---|---|
| .pdf | .pdf, .txt, .json |
| .csv | .csv, .pdf, .txt, .json |
| .txt | .pdf, .txt, .json |

<p align="center">
  <img src="media/De-identification flow.png" alt="De-identification flow" width="1000"/>
</p>

---

## Repository structure

```
deduce_pipeline/
    __init__.py       # unified run_pipeline() — auto-detects PDF vs CSV vs TXT
    __main__.py       # CLI entry point:  python -m deduce_pipeline
    core.py           # shared utilities (DEDUCE init, text helpers, writers)
    pdf.py            # PDF-specific pipeline
    csv.py            # CSV-specific pipeline
    txt.py            # TXT-specific pipeline
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

Input type (PDF, CSV, or TXT) is **auto-detected from the file extension**.  
Run `python -m deduce_pipeline --help` for the full option listing.

#### Options

| Option | Values | Default | Description |
|---|---|---|---|
| `--mode` | `deduce` \| `custom` \| `both` | `both` | Which de-identification variant(s) to produce |
| `--format` | `pdf` `txt` `json` `csv` | `pdf` | Output format(s); combine freely |
| `--outdir` | path | `Output` | Root output directory |
| `--no-logfile` | flag | — | Disable the DEDUCE warning log |
| `--log-dir` | path | `Logs` | Directory for log files |

**CSV-specific options** (ignored for PDF/TXT input):

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

# TXT input
run_pipeline(Path("Input/document.txt"), mode="custom", formats=["pdf", "txt"])

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
| Single TXT | `Input/document1.txt` |
| All TXTs in a folder | `Input/*.txt` (shell glob) |
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

# All TXTs in Input/, custom mode, TXT output only
python -m deduce_pipeline Input/*.txt --mode custom --format txt

# CSV → CSV (cell-by-cell, preserve structure), skip the ID column
python -m deduce_pipeline Input/data.csv --format csv --skip-columns PatientID

# CSV → PDF and JSON (flat-text), deduce mode, semicolon delimiter
python -m deduce_pipeline Input/data.csv --mode deduce --format pdf json --delimiter ";"

# Multiple PDFs, no log file, custom output directory
python -m deduce_pipeline Input/A.pdf Input/B.pdf --mode both --format pdf --outdir Results --no-logfile
```

### Output file naming

Files are grouped inside `--outdir` under a **subject-level folder**, derived from the input path via `core.extract_subject_id`:

| Layout | Example input | Subject ID |
|---|---|---|
| Flat | `Input/0001184_admission.pdf` | `0001184` |
| Nested | `Input/1184/admission.pdf` | `1184` (parent folder name) |
| Fallback | `Input/document1.pdf` | `document1` (filename stem) |

Within each subject folder, output files are suffixed `_deidd` (original DEDUCE-only output) or `_deidc` (DEDUCE + custom post-processing). PDF and TXT input are prefixed with the subject ID; CSV flat-text output uses the input filename stem only:

```
Output/
  1184/
    1184_admission_deidd.pdf   ← Only original DEDUCE output
    1184_admission_deidc.pdf   ← + custom post-processing step
    1184_admission_deidc.txt
    1184_admission_deidd.json
  data/
    data_deidc.csv
    data_deidd.csv
```

---

## Pipeline internals

### 1. Preprocessing

- **Text extraction**: `pdfplumber` (PDF), row concatenation (CSV flat-text mode), or a plain UTF-8 read (TXT)
- **CID code replacement**: `(cid:431)` → `ff`, `(cid:432)` → `ffi`, `(cid:433)` → `ffl`
- **CamelCase splitting**: `drNaamJohannes` → `dr Naam Johannes`

### 2. DEDUCE de-identification

The DEDUCE NER engine detects direct identifiers (names, phone numbers, email addresses, locations). Only warnings are logged; no PHI is written to stdout.

### 3. Custom post-processing (`custom` mode)

Applied on top of DEDUCE output:

| Identifier type | Rule |
|---|---|
| Age | Numeric age → `[LEEFTIJD <35]`, `[LEEFTIJD 35-50]`, `[LEEFTIJD 50-65]`, `[LEEFTIJD 65-70]`, `[LEEFTIJD 70-75]`, or `[LEEFTIJD 75+]`; non-numeric → `[LEEFTIJD ONBEKEND]` |
| Years (yyyy) | Newest year → `[JAAR 0]`, earlier → `[JAAR -1]`, `[JAAR -3]`, etc. |
| Full dates (dd-mm-yyyy) | → `[DATUM]` |
| Partial dates (dd/mm, dd-mm) | → `[DATUM]` |
| Dutch month names | → `[MAAND]` |
| Clock times (`14:30`, `9u`, `14 uur`) | → `[TIJD]` |
| Weekdays, abbreviations, named "dag" occasions (`verjaardag`, `kerstdag`, ...) | → `[DAG]` |
| Known staff names, hospitals, countries, languages missed by DEDUCE | → `[PERSOON]`, `[ZIEKENHUIS]`, `[LAND]`, `[TAAL]` (fixed term lists in `core.py`) |
| Person names in cardiology jargon | → Preserved (whitelist) |

##### Medical terms whitelist

Eponymous terms are preserved to maintain clinical relevance: Glasgow, Barthel, Brugada, Wellens, De Winter, Wells, Sgarbossa, Murphy, circle of Willis, and many more. See `core.get_medical_terms_whitelist()` for the full list.

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

All 36 tests cover core utilities, the PDF and CSV pipelines, all output formats, and the CLI. (The TXT pipeline currently has no dedicated tests.)

---

## License

Provided as-is for research and demonstration purposes.