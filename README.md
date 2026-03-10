# DEDUCE De-identification Pipelines

This repository contains two small Python pipelines that demonstrate how to
use the [**DEDUCE**](https://pypi.org/project/deduce) library to de‑identify
Dutch free-text in the domain of cardiology. Text can be extracted from either 
PDF documents or CSV files, and is returned into a PDF document.
The goal is to provide a minimal, secure workflow that can be executed from 
the command line or imported as a library.  All code is written in English 
with comprehensive docstrings.

## Research context and motivation

These pipelines were developed as part of a **clinical AI validation study at Erasmus MC**.  
The study aims to validate a multi-agent, multi-modal clinical decision support (CDS) tool 
based on large language models (LLMs) combined with Retrieval-Augmented Generation (RAG) 
on international cardiology guidelines. The prototype is designed to support guideline-based 
clinical reasoning for cardiologists in acute settings.

### Two-phase anonymization workflow

To remain compliant with **GDPR/AVG** while enabling research on real-world cardiology 
discharge reports, the study employs a two-phase anonymization strategy:

1. **Automated de-identification (Phase 1)**  
   The DEDUCE engine performs Named Entity Recognition (NER) to identify direct and 
   quasi-identifiers. This repository implements this phase as a secure, self-contained 
   pipeline that:
   - Does not make external API calls
   - Writes cache/log files locally only
   - Operates on a local server environment
   - Adheres to the **HIPAA Safe Harbor standard** for automated de-identification

2. **Manual review (Phase 2)**  
   Two independent human assessors manually verify the output to correct any residual 
   identifiers and generalize indirect identifiers (e.g., rare comorbidities) that 
   automated tools may miss. This ensures **100% recall** of personal information.

### Identifier categorization

The pipeline follows the research protocol's classification of identifiers:

| **Category** | **Treatment** | **Purpose** |
|---|---|---|
| **Direct identifiers** | Fully redacted (no clinical utility) | Names, contact details, addresses |
| **Quasi-identifiers** | Generalized/transformed (preserved clinically) | Age (→ categories), dates (→ relative shifts) |
| **Clinical information** | Preserved as-is | Medical history, medication, eponymous scales |

This hybrid approach balances privacy protection with the preservation of clinically 
relevant information essential for guideline-based AI reasoning.

## Repository structure

```
├── deduce_pipeline/          # shared package code
│   ├── __init__.py
│   ├── core.py               # shared helpers and utilities
│   ├── pdf.py                # PDF-specific pipeline
│   └── csv.py                # CSV-specific pipeline
├── main.py                   # simple driver script
├── deduce_pdf_pipeline.py    # compatibility wrapper
├── deduce_csv_pipeline.py    # compatibility wrapper
├── tests/                    # pytest tests
│   ├── test_core.py
│   └── test_pipelines.py
├── requirements.txt          # runtime dependencies
└── README.md                 # this file
```

## Pipeline structure and additions to the original DEDUCE

Original DEDUCE repository: https://github.com/vmenger/deduce

### 1. Preprocessing

Before passing text to DEDUCE, the pipeline applies the following transformations:

- **Text extraction**: Extract readable text from PDF documents (using `pdfplumber`) or from CSV files (concatenating all rows and columns).
- **CID code replacement**: PDF extraction sometimes produces character ID codes like `(cid:431)` when fonts/ligatures cannot be decoded. These are replaced with likely characters (`ff`, `ffi`, `ffl`).
- **CamelCase splitting**: Insert spaces between words joined in CamelCase (e.g., `drNaamJohannes` → `dr Naam Johannes`), making tokenization for DEDUCE more reliable.

### 2. DEDUCE de-identification

The core DEDUCE engine identifies and removes protected health information (PHI) such as person names, phone numbers, email addresses, and locations. The engine uses a pre-trained model trained on Dutch medical text.

Logging is configured to capture warnings only (no sensitive data to stdout); cache directories are created with restricted permissions (mode 700 when possible).

### 3. Post-processing

#### Direct identifiers (fully anonymized)

- **Person identification**: DEDUCE identifies `PERSOON` tags. The first one encountered is marked as `[PATIËNT]` (the patient); all others are replaced with `[PERSOON]` (other people mentioned in the document).
- **Contact information**: Email addresses → `[EMAIL]`, phone numbers → `[TELEFOONNUMMER]`, locations → `[LOCATIE]`.

#### Quasi-identifiers (categorized/shifted)

- **Age categorization**: Numeric age values are replaced with brackets:
  - Age ≥ 50 → `[Leeftijd >=50]`
  - Age < 50 → `[Leeftijd <50]`
  - Unparseable values → `[Leeftijd onbekend]`
- **Temporal shifting**: Dates are detected and replaced with `[DATUM]`. Four-digit years are shifted relative to the newest year found (newest → `[JAAR 0]`, earlier years → `[JAAR -3]`, etc.).
- **Month anonymization**: Dutch month names (full and abbreviated: januari, jan, februar, etc.) are replaced with `[MAAND]`.

#### Clinical information (preservation)

Medical terms that happen to be eponymous (named after people) are preserved to maintain clinical relevance:

- **Scores & scales**: Apgar, Glasgow, Barthel, MMSE, Karnofsky, ECOG, ASA, Mallampati, Bromage, Ramsay, Aldrete, Stevens, NRS, VAS, FPS, Kilip, Forrester, Wells, Sgarbossa, Chadvasc, etc.
- **Signs & syndromes**: Kussmaul, Cheyne-Stokes, Biot, Brugada, Long QT, Wolff-Parkinson-White, Wellens, De Winter, Osborn, etc.
- **Anatomical structures**: Circle of Willis, Foramen of Monro, Aqueduct of Sylvius, Ampulla of Vater, Triangle of Koch, etc.
- **Clinical signs**: Pemberton's sign, Rovsing's sign, Murphy's sign, Blumberg's sign, McBurney's point, etc.

These terms are detected in a whitelist and filtered out of the annotation results before placeholder replacement, ensuring they remain readable in the output.


## Installation

1. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # on Windows
   # or `source .venv/bin/activate` on macOS/Linux
   ```
2. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) install development dependencies:
   ```bash
   pip install pytest
   ```

## Usage

### As a library

Both pipelines expose a `run_pipeline` function with identical arguments.
Example:

```python
from pathlib import Path
from deduce_pipeline.csv import run_pipeline

run_pipeline(
    input_csv=Path("Input/data.csv"),
    output_custom_pdf=Path("Output/data_custom.pdf"),
    output_deduce_pdf=Path("Output/data_deduce.pdf"),
    output_dir=Path("Output"),
    write_log_file=True,
)
```

### From the command line

Each module provides a CLI entry point; run them directly or via the
compatibility wrappers:

```bash
python deduce_pipeline/csv.py --input Input/data.csv --outdir Output
python deduce_pipeline/pdf.py --input Input/document.pdf --outdir Output
```

You can also execute `main.py` to process multiple files in a simple loop.
Edit the script to toggle the PDF/CSV pipelines and specify the input
lists.

### Output

Each pipeline produces one or two PDF files:

* `<basename>_deduce.pdf` – the de‑identified text produced only by
  DEDUCE.
* `<basename>_custom.pdf` – the result after additional custom
  post‑processing (age categorization, placeholder mapping, month/year
  anonymization).

A log file containing warnings from the DEDUCE engine is written when
enabled.

## Testing

Run the automated tests with:

```bash
python -m pytest
```

The tests cover the core utilities as well as both pipelines and ensure
that basic functionality remains intact.

## Compliance & Security

This pipeline is designed to meet the requirements of **GDPR/AVG** and **HIPAA Safe Harbor** 
standards for automated de‑identification:

### Key security features

- **Secure cache directory**: DEDUCE cache paths are created with permissions `0o700` 
  (user read/write only) whenever possible.
- **No external API calls**: All processing happens locally; no data is sent to external servers.
- **Restricted logging**: Only warnings from DEDUCE are logged (no PHI in stdout/stderr).
  Log files are written to secure, restricted-access directories.
- **Compliance check**: The pipeline implements the **HIPAA Safe Harbor method** for Safe Harbor 
  de‑identification, which allows 18 specific identifier types to remain if properly generalized 
  or redacted.

### Data flow

```
EPD / Local files
    ↓
[Internal pseudonymization with study codes]
    ↓
[Automatic de-identification: DEDUCE NER engine]
    ↓
[Custom post-processing: generalization, placeholder mapping]
    ↓
[Output: two-phase anonymized documents]
    ↓
[Manual review by independent assessors (Phase 2)]
```

For research at Erasmus MC or similar institutions, the automated output from this 
pipeline should be treated as Phase 1. The manual review step (Phase 2) is essential 
for ensuring 100% recall on all personal information.

## License

This code is provided as-is for demonstration purposes.
