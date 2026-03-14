from __future__ import annotations
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
from utils.field_extractor import run_extraction
from pathlib import Path
from typing import Any, Dict, Optional
import html
import pikepdf
import re
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Sequence
import tempfile
import pikepdf
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation
import unicodedata
from datetime import datetime

# -------------------------------
# Parsing logic (Due Date & Amount)
# -------------------------------
MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_LONG = rf"{MONTH}\s+\d{{1,2}},\s+\d{{4}}"   # e.g., August 28, 2025
DATE_DMY  = r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}"  # 06 Oct 2025
DATE_ANY  = rf"(?:{DATE_LONG}|{DATE_DMY})"

MONEY_CORE = r"\d{1,3}(?:,\d{3})*(?:\.\d{2})?"
MONEY = rf"(?:[\(]?\s*(?:₱|P)?\s*{MONEY_CORE}\s*[\)]?)"  # optional ₱/P, parentheses
_MONEY_RE = re.compile(
    r"""
    ^\s*
    (?P<sign>[-+])?
    \s*
    (?P<cur>(?:₱|[Pp]))?   # optional currency
    \s*
    (?P<num>\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{1,2}))?
    \s*
    (?P<suf>CR|DR)?        # optional CR/DR
    \s*$
    """,
    re.VERBOSE
)

DATE_FORMATS = [
    "%Y-%m-%d",          # 2026-02-18
    "%B %d, %Y",         # January 28, 2026
    "%b %d, %Y",         # Jan 28, 2026
    "%m/%d/%Y",          # 02/18/2026
    "%d %B %Y",          # 18 February 2026
    "%d %b %Y",          # 18 Feb 2026
]

def parse_date(text: str):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            print(f"Date '{text}' does not match format '{fmt}'")
            pass
    raise ValueError(f"Unrecognized date format: {text}")

def parse_money(s: str, *, return_cents: bool = False):
    """
    Parse a money string to Decimal (default) or integer cents.

    Examples handled:
      '₱ 13,927.33', '13,927.33CR', '(13,927.33)', 'P1,000', '-850', '850.0'
    Returns None on empty/invalid input.
    """
    if s is None or s == "":
        return None

    if isinstance(s, Decimal):
        q = s
        q = q.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        return int((q * 100).to_integral_value(rounding=ROUND_HALF_EVEN)) if return_cents else q

    if isinstance(s, int):
        q = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        return int((q * 100).to_integral_value(rounding=ROUND_HALF_EVEN)) if return_cents else q

    if isinstance(s, float):
        q = Decimal(str(s)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        return int((q * 100).to_integral_value(rounding=ROUND_HALF_EVEN)) if return_cents else q

    s = str(s).strip()
    s = unicodedata.normalize("NFKC", s)

    paren_neg = s.startswith("(") and s.endswith(")")
    if paren_neg:
        s = s[1:-1].strip()

    m = _MONEY_RE.match(s)
    if not m:
        return None

    sign = m.group("sign") or ""
    num = m.group("num").replace(",", "")
    suf = (m.group("suf") or "").upper()
    frac = m.group(4)

    try:
        q = Decimal(num + (("." + frac) if frac else ""))
    except InvalidOperation:
        return None

    is_credit_negative = (suf == "CR")
    is_debit_positive = (suf == "DR")
    negative = paren_neg or (sign == "-") or is_credit_negative

    if negative and not is_debit_positive:
        q = -q

    q = q.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

    if return_cents:
        return int((q * 100).to_integral_value(rounding=ROUND_HALF_EVEN))
    return q

# -------------------------------
# Helpers: decrypt + preprocessing
# -------------------------------

def decrypt_to_temp(
    encrypted_pdf: str,
    password: Optional[str] = None,
    useful_page: Optional[Sequence[int]] = None,
) -> str:
    """
    Open a PDF and save selected pages into an unencrypted temporary PDF.

    Args:
        encrypted_pdf: Path to the source PDF.
        password: Password for encrypted PDFs. Leave as None for unencrypted PDFs.
        useful_page: 1-based page numbers to extract. Defaults to [1].

    Returns:
        Path to the temporary decrypted PDF.

    Raises:
        FileNotFoundError: If the input PDF does not exist.
        ValueError: If the PDF is encrypted and password is missing/wrong,
                    or if no valid pages are selected.
    """
    src = Path(encrypted_pdf)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {encrypted_pdf}")

    pages_to_extract = list(useful_page) if useful_page is not None else [1]

    if not pages_to_extract:
        raise ValueError("useful_page cannot be empty.")

    if not all(isinstance(pg, int) and pg >= 1 for pg in pages_to_extract):
        raise ValueError("All page numbers in useful_page must be positive integers.")

    try:
        open_kwargs = {"password": password} if password is not None else {}

        with pikepdf.open(str(src), **open_kwargs) as pdf:
            new_pdf = pikepdf.Pdf.new()

            for pg in pages_to_extract:
                if pg > len(pdf.pages):
                    continue
                new_pdf.pages.append(pdf.pages[pg - 1])

            if len(new_pdf.pages) == 0:
                raise ValueError(
                    f"No valid pages selected. PDF has {len(pdf.pages)} page(s), "
                    f"but requested pages were: {pages_to_extract}"
                )

            fd, tmp_name = tempfile.mkstemp(
                prefix=src.stem + ".",
                suffix=".decrypted.tmp.pdf"
            )
            Path(tmp_name).unlink(missing_ok=True)  # remove empty file created by mkstemp

            tmp_path = Path(tmp_name)
            try:
                new_pdf.save(str(tmp_path))
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

            return str(tmp_path)

    except pikepdf.PasswordError:
        if password is None:
            raise ValueError("PDF is encrypted — provide the correct password to decrypt.")
        raise ValueError("PDF is encrypted and the provided password is incorrect.")

def get_text_from_pdf(pdf_path: str, lang: str = "eng") -> str:
    """
    Extract text from a PDF using Docling + Tesseract OCR when needed.
    """
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = False

    ocr_options = TesseractCliOcrOptions(
        lang=[lang],
        force_full_page_ocr=True,
    )

    pipeline_options.ocr_options = ocr_options

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            )
        }
    )

    result = converter.convert(pdf_path)
    return result.document.export_to_markdown()

def preprocess_statement_text(raw_text: str) -> str:
    text = raw_text

    # 1) HTML unescape
    text = html.unescape(text)

    # 2) Remove markdown image placeholders
    text = re.sub(r"<!--\s*image\s*-->", " ", text, flags=re.I)

    # 3) Remove markdown table separator lines like |-----|
    text = re.sub(r"^\|[-|]+\|?$", " ", text, flags=re.M)

    # 4) Remove very large fee/table block starting from the big table until before statement header
    #    Keep this targeted so we preserve the useful bottom section.
    text = re.sub(
        r"\|?\s*RATES\s+AND\s+FEES\s+TABLE.*?(?=STATEMENT\s+DATE\s+CUSTOMER\s+NUMBER)",
        " ",
        text,
        flags=re.I | re.S,
    )

    # 5) Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 6) Replace multiple spaces/tabs with single space
    text = re.sub(r"[ \t]+", " ", text)

    # 7) Remove excessive blank lines
    text = re.sub(r"\n{2,}", "\n\n", text)

    # 8) Strip each line
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]

    # 9) Optional: keep only likely useful lines
    useful_patterns = [
        r"\bBPI\b",
        r"\bHSBC\b",
        r"\bPrepared for\b",
        r"\bSTATEMENT\s+DATE\b",
        r"\bCUSTOMER\s+NUMBER\b",
        r"\bJANUARY\b|\bFEBRUARY\b|\bMARCH\b|\bAPRIL\b|\bMAY\b|\bJUNE\b|\bJULY\b|\bAUGUST\b|\bSEPTEMBER\b|\bOCTOBER\b|\bNOVEMBER\b|\bDECEMBER\b",
        r"\b\d{4,}[-\d]*\b",  # customer/account-like numbers
        r"\bUpdated\b",
        r"\b20\d{2}\b",
        r"\bBlk\b|\bLot\b|\bStreet\b|\bCity\b",
        r"\b₱\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b",  # money amounts with ₱
        r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*(?:CR|DR)?\b",  # money amounts
        r"\bCredit\s+Limit\b",
        r"\bTotal\s+Amount\s+Due\b",
        r"\bMinimum\s+Amount\s+Due\b",
    ]

    kept = []
    for line in lines:
        if any(re.search(p, line, flags=re.I) for p in useful_patterns):
            kept.append(line)

    # 10) Deduplicate consecutive identical lines
    cleaned = []
    prev = None
    for line in kept:
        if line != prev:
            cleaned.append(line)
        prev = line

    return "\n".join(cleaned)


def extract_bill_fields(
        encrypted_pdf: str, 
        password: str, lang: str = "eng", 
        useful_page: list[int] = [1], 
        model: Optional[Any] = None, 
        tokenizer: Optional[Any] = None) -> Dict[str, Optional[str]]:
    
    dec_path = decrypt_to_temp(encrypted_pdf, password, useful_page)
    text = get_text_from_pdf(dec_path, lang=lang)
    pre_processed_text = preprocess_statement_text(text)
    print(pre_processed_text)

    out = run_extraction(pre_processed_text, tokenizer=tokenizer, model=model)

    print(out)

    validated = out.get("validated", None)
    if not validated:
        raise ValueError("Extraction failed validation checks. Output may be unreliable.")
   
    validated["total_amount_due"] = parse_money(validated.get("total_amount_due"))
    validated["minimum_amount_due"] = parse_money(validated.get("minimum_amount_due"))
    validated["credit_limit"] = parse_money(validated.get("credit_limit"))
    validated["payment_due_date"] = parse_date(validated["payment_due_date"])
    validated["statement_date"] = parse_date(validated["statement_date"])

    if validated["total_amount_due"] > validated["credit_limit"]:
        limit = validated["total_amount_due"]
        validated["total_amount_due"] = validated["credit_limit"]
        validated["credit_limit"] = limit

    # Clean up decrypted temp file
    try:
        shutil.move(dec_path, encrypted_pdf)
        # Ensure tempfile is gone
        if dec_path.exists():
            dec_path.unlink(missing_ok=True)
    except Exception:
        pass
    return validated

if __name__ == "__main__":
    pass