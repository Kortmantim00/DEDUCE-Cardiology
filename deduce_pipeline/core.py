"""Shared utilities for DEDUCE pipelines.

This module centralizes common functionality used by both the PDF and CSV
pipelines, making the code easier to maintain and review. It includes:

* secure initialization of the :class:`deduce.Deduce` instance with
temporary cache directories and optional logging
* PDF writing helpers (ReportLab wrappers)
* Text preprocessing, CID code fixes, and anonymization helpers
* Custom de‑identification post‑processing on top of DEDUCE output

All functions are written in English and thoroughly documented for
GitHub representation.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Iterable

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from deduce import Deduce


# ---------------------------------------------------------------------------
# secure Deduce initialization
# ---------------------------------------------------------------------------

@dataclass
class SecureDeduce:
    """Container holding a :class:`deduce.Deduce` instance along with
    supporting objects that must remain alive for the duration of a run.

    The temporary directory is kept as an attribute so that it isn't
    garbage‑collected before the caller is finished with the cache/log
    files.
    """

    deduce: Deduce
    tempdir: tempfile.TemporaryDirectory
    log_file: Optional[Path]


def init_deduce_secure(write_log_file: bool = True, log_dir: Path | None = None) -> SecureDeduce:
    """Initialize a **secure** Deduce instance.

    The returned object contains a :class:`Deduce` instance whose cache
    directory has mode ``700`` (when possible) and which is configured
    to log warnings only.  If ``write_log_file`` is ``True`` a file
    handler is installed; the caller is responsible for calling
    :func:`close_logging_handlers` before the temporary directory is
    cleaned up.

    Args:
        write_log_file: whether to add a file handler for warnings.
        log_dir: explicit directory to write the logfile to; if ``None`` a
            safe temporary directory is used.

    Returns:
        A :class:`SecureDeduce` container.
    """
    tmp = tempfile.TemporaryDirectory()

    # choose cache path
    if log_dir:
        cache_path = Path(log_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
    else:
        cache_path = Path(tmp.name)

    # try to make it private; ignore failures (Windows, etc.)
    try:
        os.chmod(cache_path, 0o700)
    except Exception:  # pragma: no cover - best effort
        pass

    # reset root logger to warnings only and remove existing handlers
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.WARNING)

    log_file: Optional[Path] = None
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


def close_logging_handlers() -> None:
    """Close all file handlers attached to the root logger.

    The runner should call this before allowing the temporary directory to
    be removed; otherwise the logfile may remain locked on Windows.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            handler.close()
            root.removeHandler(handler)


# ---------------------------------------------------------------------------
# PDF writing helpers
# ---------------------------------------------------------------------------


def _register_font_if_available() -> str:
    """Attempt to register a Unicode TrueType font for ReportLab.

    If one of the well‑known font paths exists the font is registered as
    ``UserFont`` and its name returned.  Otherwise ``Helvetica`` is
    used as a fallback.

    Returns:
        The font name to use in paragraph styles.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            font_name = "UserFont"
            try:
                pdfmetrics.registerFont(TTFont(font_name, p))
                return font_name
            except Exception:  # pragma: no cover - best effort
                pass
    return "Helvetica"


def write_text_to_pdf(text: str, output_pdf: Path, title: str) -> None:
    """Render ``text`` into a simple PDF document.

    Paragraph wrapping and basic styling are handled via ReportLab's
    :class:`SimpleDocTemplate` and default stylesheet.

    Args:
        text: The body text to write.  Blank strings are accepted.
        output_pdf: Destination file (parent directories will be created).
        title: Title to display on the first page.
    """
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    font_name = _register_font_if_available()

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.fontName = font_name

    normal = styles["Normal"]
    normal.fontName = font_name
    normal.fontSize = 11
    normal.leading = 14

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=24,
    )

    story = [Paragraph(title, title_style), Spacer(1, 12)]
    for para in (text or "").split("\n\n"):
        para = para.replace("\n", "<br/>")
        story.append(Paragraph(para, normal))
        story.append(Spacer(1, 8))

    doc.build(story)


def write_text_to_txt(text: str, output_path: Path) -> None:
    """Write ``text`` as a plain UTF-8 text file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def write_text_to_json(
    text: str,
    output_path: Path,
    source_file: str,
    admission_data: str = "",
    diagnosis_and_plan: str = "",
) -> None:
    """Write ``text`` as a JSON file with metadata and optional split sections."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_file": source_file,
        "processed_at": datetime.datetime.now().isoformat(),
        "deidentified_text": text,
        "admission_data": admission_data,
        "diagnosis_and_plan": diagnosis_and_plan,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# section splitting
# ---------------------------------------------------------------------------

# Names not reliably detected by DEDUCE that should always become [PERSOON]
_CUSTOM_PERSON_NAMES: list[str] = [
    "Jewbali", "Boon", "Dubois", "Akkerhuis", "Bunge", "Kimmann", "Ghossein",
]

# (prefix, bucket) — prefix is matched case-insensitively at line start
_SECTION_RULES: list[tuple[str, str]] = [
    ("reden van opname",          "admission"),
    ("reden opname",              "admission"),
    ("voorgeschiedenis",          "admission"),
    ("anamnese",                  "admission"),
    ("allergi",                   "admission"),  # allergieën, allergies
    ("lichamelijk onderzoek",     "admission"),
    ("electrocardiogram",         "admission"),
    ("laboratorium",              "admission"),  # laboratorium onderzoek / laboratoriumonderzoek
    ("radiologie",                "admission"),
    ("echocardiogram",            "admission"),
    ("coronairangiogram",         "admission"),
    ("klinische elektrofysiologie", "admission"),
    ("bespreking",                "plan"),
    ("conclusie",                 "plan"),
    ("beleid",                    "plan"),
    ("medicatie",                 "plan"),
]


def _bucket_for_header(matched_text: str) -> str:
    key = matched_text.lower()
    for prefix, bucket in _SECTION_RULES:
        if key.startswith(prefix):
            return bucket
    return "admission"


def split_sections(text: str) -> Tuple[str, str]:
    """Split de-identified text into admission data and diagnosis/plan.

    Uses known Dutch discharge-letter section headers to assign each block
    to one of two buckets.  Text before the first recognised header is
    included in admission data.

    Returns:
        ``(admission_data, diagnosis_and_plan)``
    """
    prefixes = [re.escape(rule[0]) for rule in _SECTION_RULES]
    pattern = re.compile(
        r"(?m)^(" + "|".join(prefixes) + r")[^:\n]*:",
        re.IGNORECASE,
    )

    matches = list(pattern.finditer(text))
    if not matches:
        return text, ""

    admission_parts: list[str] = []
    plan_parts: list[str] = []

    # text before the first recognised header → admission
    intro = text[: matches[0].start()].strip()
    if intro:
        admission_parts.append(intro)

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        bucket = _bucket_for_header(match.group(1))
        if bucket == "plan":
            plan_parts.append(chunk)
        else:
            admission_parts.append(chunk)

    return "\n\n".join(admission_parts), "\n\n".join(plan_parts)


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------


def preprocess_text(text: str) -> str:
    """Insert spaces in CamelCase words.

    This makes strings such as ``"patientJohn"`` or
    ``"drNaamJohannes"`` easier for DEDUCE to interpret as separate
    tokens.
    """
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)


# the whitelist is reused by both pipelines; exposing getter makes it easier
# to test

def get_medical_terms_whitelist() -> set[str]:
    """Return a set of lowercase medical terms that should *not* be
    anonymized because they are eponymous or otherwise patient‑neutral.
    """
    return {
        "apgar",
        "glasgow",
        "barthel",
        "mini mental state",
        "mmse",
        "folstein",
        "karnofsky",
        "ecog",
        "who",
        "asa",
        "mallampati",
        "bromage",
        "ramsay",
        "aldrete",
        "stevens",
        "pain scale",
        "numeric rating scale",
        "nrs",
        "visual analogue scale",
        "vas",
        "faces pain scale",
        "fps",
        "kilip",
        "forrester",
        "wells",
        "sgarbossa",
        "smith",
        "chadvasc",
        "kussmaul",
        "cheyne stokes",
        "biot",
        "atrial fibrillation",
        "afib",
        "ventricular tachycardia",
        "vtach",
        "torsades de pointes",
        "tdp",
        "brugada",
        "long qt syndrome",
        "lqts",
        "wolff parkinson white",
        "wpw",
        "ekg",
        "ecg",
        "electrocardiogram",
        "wellens",
        "de winter",
        "osborn",
        "cabrera",
        "ewart",
        "levine",
        "beck",
        "hamman",
        "seldinger",
        "circle of willis",
        "foramen of monro",
        "aqueduct of sylvius",
        "duct of wirsung",
        "ampulla of vater",
        "triangle of koch",
        "hepatojugular reflux",
        "hepatojugular",
        "hepato-jugular",
        "pemberton",
        "pemberton's sign",
        "rovsing",
        "rovsing's sign",
        "murphy",
        "murphy's sign",
        "blumberg",
        "blumberg's sign",
        "mc burney",
        "mcburney",
        "mcburney's point",
        "balthazar",
    }


def filter_medical_terms(annotations: Iterable) -> list:
    """Return a new list of annotations omitting medical terms.

    An annotation object is expected to have ``tag`` and ``text``
    attributes.  Matching is case‑insensitive.  Any annotation whose text
    exactly matches a whitelisted term is dropped; a heuristic also skips
    annotations that are a short phrase containing a whitelisted term.
    """
    whitelist = get_medical_terms_whitelist()
    out = []
    for ann in annotations:
        tag = getattr(ann, "tag", "").lower()
        text = getattr(ann, "text", "").lower().strip()
        if text in whitelist:
            continue
        for term in whitelist:
            if term in text and len(text) <= len(term) + 10:
                break
        else:  # not broken
            out.append(ann)
    return out


def fix_cid_codes(text: str) -> str:
    """Replace common PDF "cid" ligature codes with likely characters.

    When ``pdfplumber`` fails to decode certain ligatures it inserts tokens
    such as ``"(cid:431)"``.  These are usually ``ff``/``ffi``/``ffl``.
    """
    cid_mapping = {"(cid:431)": "ff", "(cid:432)": "ffi", "(cid:433)": "ffl"}
    result = text
    for cid_code, replacement in cid_mapping.items():
        result = result.replace(cid_code, replacement)
    return result


def anonymize_months(text: str) -> str:
    """Replace Dutch month names (full and abbreviated) with ``[MAAND]``.

    The replacement is case‑insensitive and handles common abbreviations.
    """
    month_patterns = [
        (r"\bjanuar[iy]\b", "[MAAND]"),
        (r"\bjan(?:\.|uari|uary)?\b", "[MAAND]"),
        (r"\bfebru?ar[iy]\b", "[MAAND]"),
        (r"\bfeb(?:\.|ruary)?\b", "[MAAND]"),
        (r"\bmaart\b", "[MAAND]"),
        (r"\bmrt\.?\b", "[MAAND]"),
        (r"\bapril\b", "[MAAND]"),
        (r"\bapr(?:\.|il)?\b", "[MAAND]"),
        (r"\bmei\b", "[MAAND]"),
        (r"\bjuni\b", "[MAAND]"),
        (r"\bjun(?:\.|i)?\b", "[MAAND]"),
        (r"\bjuli\b", "[MAAND]"),
        (r"\bjul(?:\.|i)?\b", "[MAAND]"),
        (r"\baugustus\b", "[MAAND]"),
        (r"\baug(?:\.|ustus)?\b", "[MAAND]"),
        (r"\bseptember\b", "[MAAND]"),
        (r"\bsep(?:\.|tember)?\b", "[MAAND]"),
        (r"\boktober\b", "[MAAND]"),
        (r"\bokt(?:\.|ober)?\b", "[MAAND]"),
        (r"\bnovember\b", "[MAAND]"),
        (r"\bnov(?:\.|ember)?\b", "[MAAND]"),
        (r"\bdecember\b", "[MAAND]"),
        (r"\bdec(?:\.|ember)?\b", "[MAAND]"),
    ]
    result = text
    for pattern, replacement in month_patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def anonymize_years(text: str) -> str:
    """Replace 4-digit years with relative placeholders.

    Steps applied in order:
    1. Full dates (dd-mm-yyyy, dd/mm/yyyy, dd.mm.yyyy) → [DATUM]
    2. Partial dates without year (dd/mm, dd-mm) → [DATUM]
    3. YYYY-MM patterns → [JAAR x] (entire expression collapsed)
    4. Remaining standalone 4-digit years → [JAAR x]

    The newest year found becomes [JAAR 0]; earlier years are offset
    accordingly ([JAAR -1], [JAAR -3], etc.).
    """
    # Step 1: full dates dd-mm-yyyy / dd/mm/yyyy / dd.mm.yyyy
    result = re.sub(r"\b\d{1,2}[-\./]\d{1,2}[-\./](?:\d{2}|\d{4})\b", "[DATUM]", text)

    # Step 2: partial dates dd/mm and dd-mm (day 1-31, month 1-12)
    result = re.sub(
        r"\b(0?[1-9]|[12]\d|3[01])[/\-](0?[1-9]|1[0-2])\b",
        "[DATUM]",
        result,
    )

    # Determine base year from all remaining 4-digit years
    year_pattern = r"\b(19\d{2}|20\d{2})\b"
    all_years = {int(m.group(1)) for m in re.finditer(year_pattern, result)}
    if not all_years:
        return result

    base_year = max(all_years)
    year_mapping = {y: f"[JAAR {y - base_year}]" for y in all_years}

    # Step 3: YYYY-MM → [JAAR x]  (collapse the entire expression)
    def _replace_year_month(m: re.Match) -> str:
        return year_mapping.get(int(m.group(1)), f"[JAAR {int(m.group(1)) - base_year}]")

    result = re.sub(r"\b(19\d{2}|20\d{2})-(0[1-9]|1[0-2])\b", _replace_year_month, result)

    # Step 4: remaining standalone years
    for match in reversed(list(re.finditer(year_pattern, result))):
        year = int(match.group(1))
        start, end = match.span()
        result = result[:start] + year_mapping.get(year, f"[JAAR {year - base_year}]") + result[end:]

    return result


def apply_custom_deidentification(doc, original_text: str) -> Tuple[str, Optional[str]]:
    """Perform additional anonymization on top of a *Deduce* result.

    The following rules are applied in order:

    1. ``Age`` tags are replaced with either ``[Leeftijd >=50]`` or ``[Leeftijd <50]``
       (numeric decoding; fall back to ``[Leeftijd onbekend]``).
    2. ``Person`` tags: the **first** one encountered in the annotations becomes
       ``[PATIËNT]``; all others are ``[PERSOON]``.
    3. A few other tags are mapped to fixed placeholders (email, phone,
       location); all others are replaced with ``[TAG]``.

    After this function returns the caller may wish to run
    :func:`anonymize_months` and :func:`anonymize_years` on the output.

    Args:
        doc: object returned by ``deduce.deidentify``; expected to have an
            ``annotations`` iterable attribute.
        original_text: the unmodified input string; used when character
            offsets in the annotations are available.

    Returns:
        ``(processed_text, age_category)``; ``age_category`` is the string
        that replaced any age tag or ``None`` if no age was found.
    """
    age_category: Optional[str] = None
    out = original_text

    annotations = sorted(
        getattr(doc, "annotations", []),
        key=lambda a: getattr(a, "start_char", 0),
        reverse=True,
    )

    for a in annotations:
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
            placeholder = "[PERSOON]"
        elif tag == "locatie":
            # Dosages like 3500IE / 3500IU / 3500IV look like Dutch postcodes — preserve them
            if re.match(r"^\d+\s*[Ii][EeUuVv]$", orig):
                continue
            placeholder = "[LOCATIE]"
        else:
            tag_mapping = {
                "emailadres": "[EMAIL]",
                "telefoonnummer": "[TELEFOONNUMMER]",
            }
            placeholder = tag_mapping.get(tag, f"[{tag.upper()}]" if tag else "[ONBEKEND]")

        if start is not None and end is not None and 0 <= start <= end <= len(out):
            out = out[:start] + placeholder + out[end:]
        elif orig:
            out = out.replace(orig, placeholder, 1)

    # Normalize numbered DEDUCE tags: [PERSOON-1] → [PERSOON], [ZIEKENHUIS-1] → [ZIEKENHUIS]
    out = re.sub(r"\[([A-Z]+)-\d+\]", r"[\1]", out)

    # Replace names not caught by DEDUCE
    for name in _CUSTOM_PERSON_NAMES:
        out = re.sub(rf"\b{re.escape(name)}\b", "[PERSOON]", out, flags=re.IGNORECASE)

    return out, age_category
