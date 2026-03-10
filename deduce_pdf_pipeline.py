"""Backward‑compatible wrapper for the PDF pipeline.

The real implementation lives in :mod:`deduce_pipeline.pdf`.  This
module exists so that any existing scripts importing
``deduce_pdf_pipeline`` continue to work after the refactor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

# re‑export the public API from the new package
from deduce_pipeline.pdf import (
    run_pipeline,
    extract_text_from_pdf,
    INPUT_PDF,
    OUTPUT_DIR,
)

# keep the old command‑line interface for compatibility
if __name__ == "__main__":
    import sys
    from deduce_pipeline.pdf import main

    raise SystemExit(main())

# =========================
# Pipeline paden/bestanden
# =========================

# Zet hier je input PDF en doelmap:
INPUT_PDF: Path = Path("document1.pdf")
OUTPUT_DIR: Path = Path("output")

# Output bestandsnamen:
OUTPUT_PDF_CUSTOM: Path = OUTPUT_DIR / f"{INPUT_PDF.stem}_deidentified_custom.pdf"
OUTPUT_PDF_DEDUCE: Path = OUTPUT_DIR / f"{INPUT_PDF.stem}_deidentified_deduce.pdf"

# Optioneel: schrijf logs naar een tijdelijk (per-run) bestand in een beveiligde tempdir
WRITE_LOG_FILE: bool = True


# =========================
# Beveiligde Deduce setup
# =========================

@dataclass
class SecureDeduce:
    deduce: Deduce
    tempdir: tempfile.TemporaryDirectory  # reference: voorkomt vroegtijdige cleanup
    log_file: Optional[Path]


def init_deduce_secure(write_log_file: bool = True, log_dir: Path | None = None) -> SecureDeduce:
    """
    Initialiseert Deduce met:
    - beveiligde tempdir (chmod 700 indien mogelijk)
    - logging WARNING+ naar file (geen stdout/stderr handlers)
    - deduce logger: geen propagate
    
    Args:
        write_log_file: Schrijf logfile
        log_dir: Directory voor logfile; als None: gebruik tempdir
    """
    tmp = tempfile.TemporaryDirectory()
    
    # Bepaal cache/log directory
    if log_dir:
        cache_path = Path(log_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
    else:
        cache_path = Path(tmp.name)

    try:
        os.chmod(cache_path, 0o700)
    except Exception:
        pass

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.WARNING)

    log_file = None
    if write_log_file:
        log_file = cache_path / "deduce.log"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.WARNING)
        fh.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
        root.addHandler(fh)

    logging.getLogger("deduce").propagate = False
    logging.getLogger("deduce").setLevel(logging.WARNING)

    deduce = Deduce(cache_path=str(cache_path))
    return SecureDeduce(deduce=deduce, tempdir=tmp, log_file=log_file)


def _close_logging_handlers() -> None:
    """Close all file handlers to release file locks before cleanup."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            handler.close()
            root.removeHandler(handler)


# =========================
# PDF I/O
# =========================

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract alle tekst uit een PDF-bestand."""
    text_parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
    return "\n\n".join(text_parts).strip()


def _register_font_if_available() -> str:
    """
    Probeert een Unicode TTF te registreren.
    Retourneert fontnaam voor ReportLab Paragraph styles.
    """
    candidates = [
        # Linux (vaak aanwezig)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # macOS
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            font_name = "UserFont"
            try:
                pdfmetrics.registerFont(TTFont(font_name, p))
                return font_name
            except Exception:
                pass
    return "Helvetica"


def write_text_to_pdf(text: str, output_pdf: Path, title: str) -> None:
    """Schrijf tekst naar PDF (simpel, met automatische wrapping)."""
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    font_name = _register_font_if_available()

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.fontName = font_name

    normal = styles["Normal"]
    normal.fontName = font_name
    normal.fontSize = 11
    normal.leading = 14

    doc = SimpleDocTemplate(str(output_pdf), pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=24)

    story = [Paragraph(title, title_style), Spacer(1, 12)]
    # behoud linebreaks
    for para in (text or "").split("\n\n"):
        para = para.replace("\n", "<br/>")
        story.append(Paragraph(para, normal))
        story.append(Spacer(1, 8))

    doc.build(story)


# =========================
# Extra functionaliteit op DEDUCE
# =========================

import re

def _preprocess_text(text: str) -> str:
    """
    Pre-process tekst voordat DEDUCE wordt aangeroepen.
    Splitst CamelCase woorden door spaties in te voegen.
    
    Bijv: 'drNaamJohannes' → 'dr Naam Johannes'
          'patientJohn' → 'patient John'
    
    Args:
        text: Input tekst
        
    Returns:
        Pre-processed tekst met gesplitste CamelCase woorden
    """
    # Splitsen van CamelCase: voeg spatie in voor hoofdletter die volgt op kleine letter
    # Regex: (?<=[a-z])(?=[A-Z]) betekent: positie waar kleine letter gevolgd door hoofdletter
    result = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    return result


def _filter_medical_terms(annotations):
    """
    Filter annotaties om medische termen die vernoemd zijn naar personen uit te sluiten.
    Deze termen zijn scores, classificaties en signalen in het medisch domein die niet
    geanonimiseerd moeten worden.
    
    Args:
        annotations: Lijst van DEDUCE annotaties
        
    Returns:
        Gefilterde lijst van annotaties (medische termen verwijderd)
    """
    # Whitelist van medische termen vernoemd naar personen
    # Deze worden NIET geanonimiseerd
    medical_terms_whitelist = {
        # Scores en classificaties
        "apgar", "glasgow", "barthel", "mini mental state", "mmse", "folstein",
        "karnofsky", "ecog", "who", "asa", "mallampati", "bromage", "ramsay",
        "aldrete", "stevens", "pain scale", "numeric rating scale", "nrs",
        "visual analogue scale", "vas", "faces pain scale", "fps", "kilip", "Forrester",
        "Wells", "Sgarbossa", "Smith", "chadvasc",

        # Signalen en syndromen
        "kussmaul", "cheyne stokes", "biot", "atrial fibrillation", "afib",
        "ventricular tachycardia", "vtach", "torsades de pointes", "tdp",
        "brugada", "long qt syndrome", "lqts", "wolff parkinson white", "wpw",
        "ekg", "ecg", "electrocardiogram", "wellens", "de winter", "osborn",
        "cabrera", "ewart", "levine", "beck", "hamman", "seldinger",
            
        # Anatomische termen
        "circle of willis", "foramen of monro", "aqueduct of sylvius",
        "duct of wirsung", "ampulla of vater", "triangle of koch",
        
        # Andere medische termen
        "hepatojugular reflux", "hepatojugular", "hepato-jugular",
        "pemberton", "pemberton's sign", "rovsing", "rovsing's sign",
        "murphy", "murphy's sign", "blumberg", "blumberg's sign",
        "mc burney", "mcburney", "mcburney's point", "balthazar",
        
    }
    
    filtered_annotations = []
    for ann in annotations:
        tag = getattr(ann, "tag", "").lower()
        text = getattr(ann, "text", "").lower().strip()
        
        # Skip als het een medische term is
        if text in medical_terms_whitelist:
            continue
            
        # Skip als het een deel van een medische term is (bijv. "glasgow coma" in "glasgow coma scale")
        for term in medical_terms_whitelist:
            if term in text and len(text) <= len(term) + 10:  # kleine tolerantie voor extra woorden
                break
        else:
            # Niet gevonden in whitelist, behoud de annotatie
            filtered_annotations.append(ann)
    
    return filtered_annotations


def _fix_cid_codes(text: str) -> str:
    """
    Vervang CID (Character ID) codes met hun waarschijnlijke karakters.
    CID-codes ontstaan wanneer pdfplumber bepaalde fonts/ligatures niet kan decoderen.
    
    Mapping van veel voorkomende CID-codes:
    - (cid:431) → ff (ff ligature in bepaalde fonts)
    - (cid:432) → ffi (ffi ligature)
    - (cid:433) → ffl (ffl ligature)
    
    Args:
        text: Input tekst met mogelijke CID-codes
        
    Returns:
        Tekst met vervangen CID-codes
    """
    cid_mapping = {
        '(cid:431)': 'ff',
        '(cid:432)': 'ffi',
        '(cid:433)': 'ffl',
    }
    
    result = text
    for cid_code, replacement in cid_mapping.items():
        result = result.replace(cid_code, replacement)
    
    return result

def _anonymize_months(text: str) -> str:
    """
    Herken alle maanden (volledige namen en afkortingen in het Nederlands) en vervang met [MAAND].
    Ondersteunt: januari/jan, februari/feb, maart/mrt, april/apr, mei, juni/jun, juli/jul,
    augustus/aug, september/sep, oktober/okt, november/nov, december/dec
    
    Args:
        text: Input tekst
        
    Returns:
        Tekst met geanonimiseerde maanden
    """
    # Alle Nederlandse maanden (volledig en afkorting) - case-insensitive
    month_patterns = [
        (r'\bjanuar[iy]\b', '[MAAND]'),
        (r'\bjan(?:\.|uari|uary)?\b', '[MAAND]'),
        (r'\bfebru?ar[iy]\b', '[MAAND]'),
        (r'\bfeb(?:\.|ruary)?\b', '[MAAND]'),
        (r'\bmaart\b', '[MAAND]'),
        (r'\bmrt\.?\b', '[MAAND]'),
        (r'\bapril\b', '[MAAND]'),
        (r'\bapr(?:\.|il)?\b', '[MAAND]'),
        (r'\bmei\b', '[MAAND]'),
        (r'\bjuni\b', '[MAAND]'),
        (r'\bjun(?:\.|i)?\b', '[MAAND]'),
        (r'\bjuli\b', '[MAAND]'),
        (r'\bjul(?:\.|i)?\b', '[MAAND]'),
        (r'\baugustus\b', '[MAAND]'),
        (r'\baug(?:\.|ustus)?\b', '[MAAND]'),
        (r'\bseptember\b', '[MAAND]'),
        (r'\bsep(?:\.|tember)?\b', '[MAAND]'),
        (r'\boktober\b', '[MAAND]'),
        (r'\bokt(?:\.|ober)?\b', '[MAAND]'),
        (r'\bnovember\b', '[MAAND]'),
        (r'\bnov(?:\.|ember)?\b', '[MAAND]'),
        (r'\bdecember\b', '[MAAND]'),
        (r'\bdec(?:\.|ember)?\b', '[MAAND]'),
    ]
    
    result = text
    for pattern, replacement in month_patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def _anonymize_years(text: str) -> str:
    """
    Herken alle jaarcijfers (4-digit getallen tussen 1900 en 2099) in tekst.
    Vervang het oudste jaar met 'JAAR 0' en alle anderen met 'JAAR X'
    waarbij X het verschil is met het oudste jaar.
    
    Args:
        text: Input tekst
        
    Returns:
        Tekst met geanonimiseerde jaarcijfers
    """
    # 1) Vervang eerst duidelijke datumnotaties met [DATUM]
    # dd-mm-yyyy, dd.mm.yyyy, dd/mm/yyyy and two-digit years dd.mm.yy, dd-mm-yy
    date_pattern = r"\b\d{1,2}[-\./]\d{1,2}[-\./](?:\d{2}|\d{4})\b"
    result = re.sub(date_pattern, "[DATUM]", text)

    # 2) Vind alle overgebleven 4-cijfer jaarcijfers (1900-2099)
    year_pattern = r'\b(19\d{2}|20\d{2})\b'
    matches = list(re.finditer(year_pattern, result))

    if not matches:
        return result

    # Extraheer alle unieke jaren (als integers)
    years = sorted(set(int(m.group(1)) for m in matches))
    if not years:
        return result

    # Maak mapping: nieuwste jaar → "[JAAR 0]", rest → "[JAAR -X]" (negatief voor ouder)
    base_year = max(years)
    year_mapping = {year: f"[JAAR {year - base_year}]" for year in years}

    # Vervang van achter naar voor (om offsets te behouden)
    for match in reversed(matches):
        year = int(match.group(1))
        replacement = year_mapping.get(year, f"[JAAR {year - base_year}]")
        start, end = match.span()
        result = result[:start] + replacement + result[end:]

    return result


def apply_custom_deidentification(doc, original_text: str) -> Tuple[str, Optional[str]]:
    """
    Extra laag boven DEDUCE:
    - Leeftijd: categoriseer naar <50 / >=50 (of onbekend)
    - Jaren: oudste → JAAR 0, rest → JAAR X
    - PERSOON: eerste benoemde persoon → [PATIENT], rest → [PERSOON]
    - Overige tags: vervang met placeholders (email/telefoon/locatie), anders [TAG]
    """
    age_category: Optional[str] = None
    out = original_text

    # Twee-staps verwerking: eerst personen identficeren
    annotations = sorted(getattr(doc, "annotations", []), key=lambda a: getattr(a, "start_char", 0), reverse=True)

    # Vind de eerste PERSOON-annotatie (kleinste start_char)
    first_persoon_idx = None
    for idx, a in enumerate(reversed(annotations)):
        tag = getattr(a, "tag", "").lower()
        if tag == "persoon":
            first_persoon_idx = len(annotations) - 1 - idx
            break

    # Verwerk annotaties
    for idx, a in enumerate(annotations):
        tag = getattr(a, "tag", "").lower()
        orig = getattr(a, "text", "")
        start = getattr(a, "start_char", None)
        end = getattr(a, "end_char", None)

        if tag in ("leeftijd", "age"):
            try:
                age = int(orig)
                age_category = "[Leeftijd >=50]" if age >= 50 else "[Leeftijd <50]"
                placeholder = age_category
            except Exception:
                age_category = "[Leeftijd onbekend]"
                placeholder = age_category
        elif tag == "persoon":
            # Eerste persoon = PATIENT, rest = PERSOON
            if idx == first_persoon_idx:
                placeholder = "[PATIENT]"
            else:
                placeholder = "[PERSOON]"
        else:
            # Overige tags
            tag_mapping = {
                "emailadres": "[EMAIL]",
                "telefoonnummer": "[TELEFOONNUMMER]",
                "locatie": "[LOCATIE]",
            }
            placeholder = tag_mapping.get(tag, f"[{tag.upper()}]" if tag else "[ONBEKEND]")

        if start is not None and end is not None and 0 <= start <= end <= len(out):
            out = out[:start] + placeholder + out[end:]
        elif orig:
            out = out.replace(orig, placeholder, 1)  # Vervang eerste voorkomen

    return out, age_category

# =========================
# Pipeline runner
# =========================

def run_pipeline(
    input_pdf: Path,
    output_custom_pdf: Path | None,
    output_deduce_pdf: Path | None,
    output_dir: Path,
    write_log_file: bool = True,
    write_custom: bool = True,
    write_deduce: bool = True,
    log_dir: Path | None = None,
) -> tuple[Path | None, Path | None]:
    """Run the DEDUCE de-identification pipeline.

    Args:
        input_pdf: Path to input PDF
        output_custom_pdf: Path for custom-processed output (if write_custom=True)
        output_deduce_pdf: Path for standard DEDUCE output (if write_deduce=True)
        output_dir: Output directory (created if needed)
        write_log_file: Whether to write DEDUCE warnings to log
        write_custom: Whether to write the custom-processed output
        write_deduce: Whether to write the standard DEDUCE output
        log_dir: Directory for logfile (if None, use tempdir)

    Returns:
        Tuple of (custom_output_path_or_none, deduce_output_path_or_none)
    """
    # 1) inladen Deduce (beschermd)
    sd = init_deduce_secure(write_log_file=write_log_file, log_dir=log_dir)

    # 2) pdf input
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF niet gevonden: {input_pdf.resolve()}")

    text = extract_text_from_pdf(input_pdf)
    if not text:
        raise RuntimeError("Geen tekst uit PDF geëxtraheerd (PDF leeg of geen extracteerbare tekst).")

    # 2a) Fix CID codes (ligatures, font-encoding issues)
    text = _fix_cid_codes(text)

    # 2b) Pre-process: split CamelCase woorden
    text = _preprocess_text(text)

    # 3) DEDUCE
    doc = sd.deduce.deidentify(text)

    # 3b) Filter medische termen uit annotaties (scores/classificaties vernoemd naar personen)
    if hasattr(doc, "annotations"):
        original_annotations = getattr(doc, "annotations", [])
        filtered_annotations = _filter_medical_terms(original_annotations)
        doc.annotations = filtered_annotations

    # 4) write standard DEDUCE output first (preserve original DEDUCE behaviour)
    output_dir.mkdir(parents=True, exist_ok=True)

    custom_out = None
    deduce_out = None

    if write_deduce and output_deduce_pdf:
        write_text_to_pdf(getattr(doc, "deidentified_text", ""), output_deduce_pdf, title="Gede-identificeerd (DEDUCE)")
        deduce_out = output_deduce_pdf

    # 5) apply CUSTOM enhancements (only for custom output, after DEDUCE)
    if write_custom and output_custom_pdf:
        custom_text, _age_category = apply_custom_deidentification(doc, text)
        # Pas maand- en jaaraanonimisatie toe ná de custom-deidentificatie, en schrijf dit als CUSTOM output
        custom_text = _anonymize_months(custom_text)
        custom_text = _anonymize_years(custom_text)
        write_text_to_pdf(custom_text, output_custom_pdf, title="Gede-identificeerd (CUSTOM bovenop DEDUCE)")
        custom_out = output_custom_pdf

    # Geen PHI printen; alleen paden/status
    print(f"Input PDF:  {input_pdf.resolve()}")
    if custom_out:
        print(f"Output PDF (CUSTOM): {custom_out.resolve()}")
    if deduce_out:
        print(f"Output PDF (DEDUCE): {deduce_out.resolve()}")
    if sd.log_file:
        print(f"Log (warnings): {sd.log_file.resolve()}")

    # Sluit logging handlers voordat tempdir opgeruimd wordt
    _close_logging_handlers()

    return custom_out, deduce_out


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Minimal PDF → DEDUCE → PDF pipeline.")
    p.add_argument("--input", type=Path, default=INPUT_PDF, help="Input PDF pad")
    p.add_argument("--outdir", type=Path, default=OUTPUT_DIR, help="Output directory")
    p.add_argument("--custom", type=Path, default=None, help="Custom output PDF pad (optioneel)")
    p.add_argument("--deduce", type=Path, default=None, help="Deduce output PDF pad (optioneel)")
    p.add_argument("--no-logfile", action="store_true", help="Schrijf geen logfile (warnings)")
    p.add_argument(
        "--output-mode",
        choices=["custom", "deduce", "both"],
        default="both",
        help="Welke outputs schrijven: 'custom', 'deduce' of 'both' (default: both)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for the pipeline.

    Parses optional ``argv`` (defaults to ``sys.argv[1:]``) and invokes
    :func:`run_pipeline` with the resulting values.

    Returns an exit code (0 on success).
    """
    args = _parse_args(argv)

    input_pdf = args.input
    outdir = args.outdir

    custom_pdf = args.custom if args.custom else (outdir / f"{input_pdf.stem}_deidentified_custom.pdf")
    deduce_pdf = args.deduce if args.deduce else (outdir / f"{input_pdf.stem}_deidentified_deduce.pdf")

    # Bepaal welke outputs geschreven moeten worden
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
