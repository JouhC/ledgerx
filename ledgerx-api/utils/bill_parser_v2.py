from __future__ import annotations
import re, os, tempfile
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Union
from dateutil import parser as dtparser
import shutil

import pikepdf

import re
from datetime import datetime
from decimal import Decimal
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from utils.table_parser import extract_after_header
from decimal import Decimal, ROUND_HALF_EVEN
import unicodedata

# -------------------------------
# 1) Helpers: decrypt + text extraction
# -------------------------------
def decrypt_to_temp(encrypted_pdf: str, password: Optional[str] = None) -> str:
    """
    Open the PDF and save an unencrypted copy to a temporary file, returning its path.
    - If password is None, attempt to open without a password (works for unencrypted PDFs).
    - If the file is encrypted and no/incorrect password is provided, raises ValueError.
    Note: this does NOT bypass password protection — you must have the password.
    """
    src = Path(encrypted_pdf)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {encrypted_pdf}")

    # Make a unique temp filename to avoid collisions
    with tempfile.NamedTemporaryFile(
        prefix=src.stem + ".", suffix=".decrypted.tmp.pdf", delete=False
    ) as tf:
        tmp_path = Path(tf.name)

    try:
        # Try opening. If password is provided, pass it; otherwise try without password.
        if password is None:
            # If the file is encrypted this will raise PasswordError
            with pikepdf.open(str(src)) as pdf:
                new_pdf = pikepdf.Pdf.new()
                new_pdf.pages.append(pdf.pages[0])
                new_pdf.save(str(tmp_path))
        else:
            try:
                with pikepdf.open(str(src), password=password) as pdf:
                    new_pdf = pikepdf.Pdf.new()
                    new_pdf.pages.append(pdf.pages[0])
                    new_pdf.save(str(tmp_path))
            except pikepdf.PasswordError:
                # Give a clearer, higher-level error
                raise ValueError("PDF is encrypted and the provided password is incorrect.")
    except pikepdf.PasswordError:
        # This branch happens if password was None and the file required one
        # Clean up temp file and raise informative error
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError("PDF is encrypted — provide the correct password to decrypt.")
    except Exception:
        # On unexpected errors, try to remove temp file and re-raise
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise

    return str(tmp_path)

def get_text_from_pdf(pdf_path: str, lang: str = "eng") -> str:
    """
    Use OCR to extract text from all pages of the PDF.
    Returns the extracted text as a single string.
    """
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = False
    pipeline_options.table_structure_options.do_cell_matching = True
    ocr_options = TesseractCliOcrOptions(force_full_page_ocr=True)
    pipeline_options.ocr_options = ocr_options

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            )
        }
    )
    result = converter.convert(pdf_path)
    text = result.document.export_to_markdown()

    return text
# -------------------------------
# 2) Parsing logic (Due Date & Amount)
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

PATTERNS = {
    "total_balance": r"(?i)total\s+account\s+balance\s+([\d,]+\.\d{2})",
    "due_date": r"(?i)(?:payment\s+)?due\s+date\s+(\d{1,2}\s+\w+\s+\d{4})",
    "min_payment": r"(?i)minimum\s+payment\s+([\d,]+\.\d{2})"
}

# 2) NEW: Markdown-like table row matcher for the data row (4 cells).
#    We don't rely on the header text being perfect; we match any row of 4 cells following a header line.
TABLE_ROW = re.compile(
    rf"""
    ^\|\s*(?P<total_due>[\s₱P\(\)\d,\.]+?)\s*\|
      \s*(?P<min_due>[\s₱P\(\)\d,\.]+?)\s*\|
      \s*(?P<payment_due>{DATE_ANY})\s*\|
      \s*(?P<amount_paid>[\s₱P\(\)\d,\.]*)\|?
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)

def parse_date(s: str):
    s = " ".join(s.split())
    # Try multiple common OCR-safe formats
    fmts = ("%B %d, %Y", "%b %d, %Y", "%d %b %Y", "%d %B %Y")
    for fmt in fmts:
        try:
            # title() helps when OCR shouts (e.g., "AUGUST 28, 2025")
            return datetime.strptime(s.title(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unrecognized date format: {s!r}")

def parse_money(s: str, *, return_cents: bool = False):
    """
    Parse a money string to Decimal (default) or integer cents.

    Examples handled:
      '₱ 13,927.33', '13,927.33CR', '(13,927.33)', 'P1,000', '-850', '850.0'
    Returns None on empty/invalid input.
    """
    s = (s or "").strip()
    if not s:
        return None

    # Normalize weird spaces, etc.
    s = unicodedata.normalize("NFKC", s)
    # Quick paren-neg check (e.g., "(1,234.56)")
    paren_neg = s.startswith("(") and s.endswith(")")
    if paren_neg:
        s = s[1:-1].strip()

    m = _MONEY_RE.match(s)
    if not m:
        return None

    sign = m.group("sign") or ""
    num = m.group("num").replace(",", "")
    suf = (m.group("suf") or "").upper()

    # Build Decimal value safely
    # m.group(4) is the optional decimal digits captured by the inner group
    # But simpler: use the full matched 'num' + optional fraction we already captured in text `s`
    # Here we reconstruct explicitly:
    if "." in m.group(0):
        # Already has decimals in the source; keep as-is from num + trailing part
        # But safer to just read from num and the optional captured decimals:
        # Extract the fractional from the original string after removing commas is tricky,
        # so we directly use num (integer part) and group(4) as fractional if present.
        frac = m.group(4)
        q = Decimal(num + (("." + frac) if frac else ""))
    else:
        q = Decimal(num)

    # Determine negativity
    is_credit_negative = (suf == "CR")
    is_debit_positive  = (suf == "DR")
    negative = paren_neg or (sign == "-") or is_credit_negative
    positive = (sign == "+") or is_debit_positive

    # If both flags set, negative wins only if explicitly negative and not DR
    if negative and not is_debit_positive:
        q = -q

    # Round/quantize to 2 dp
    q = q.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

    if return_cents:
        return int((q * 100).to_integral_value(rounding=ROUND_HALF_EVEN))
    return q

def extract_fields(text: str) -> dict:
    # First try the brute-force method
    b = {}
    none_count = 0
    for key, pattern in PATTERNS.items():
        match = re.search(pattern, text)
        b[key] = match.group(1) if match else None
        if b[key] is None:
            none_count += 1
    
    if none_count == 0:
        return {
            "customer_number": None,  # not present in this layout
            "statement_date": None,   # not present in this layout
            "credit_limit": None,     # not present in this layout
            "total_amount_due": parse_money(b["total_balance"]),
            "minimum_amount_due": parse_money(b["min_payment"]),
            "payment_due_date": parse_date(b["due_date"]),
            "source_layout": "string_strict_sequence",
        }

    # Second try the markdown/table row layout
    t = TABLE_ROW.search(text)
    if t:
        d = t.groupdict()
        return {
            "customer_number": None,  # not present in this layout
            "statement_date": None,   # not present in this layout
            "credit_limit": None,     # not present in this layout
            "total_amount_due": parse_money(d["total_due"]),
            "minimum_amount_due": parse_money(d["min_due"]),
            "payment_due_date": parse_date(d["payment_due"]),
            "source_layout": "string_table_row",
        }
    
    m = extract_after_header(text)
    if m:
        m["total_amount_due"] = parse_money(m.get("total_amount_due"))
        m["minimum_amount_due"] = parse_money(m.get("minimum_amount_due"))
        m["payment_due_date"] = parse_date(m["payment_due_date"])
        return m

    raise ValueError("Could not match either strict sequence or table-row layout. Inspect OCR text and adjust patterns.")

# -------------------------------
# 3) One-call entry point
# -------------------------------
def extract_bill_fields(encrypted_pdf: str, password: str, lang: str = "eng") -> Dict[str, Optional[str]]:
    dec_path = decrypt_to_temp(encrypted_pdf, password)
    text = get_text_from_pdf(dec_path, lang=lang)
    out = extract_fields(text)
    # Clean up decrypted temp file
    try:
        shutil.move(dec_path, encrypted_pdf)
        # Ensure tempfile is gone
        if dec_path.exists():
            dec_path.unlink(missing_ok=True)
    except Exception:
        pass
    return out

def main():
    result = extract_bill_fields("./gmail_attachments_poc/20250914.pdf", password="20Oct1997814614", lang="eng")
    #print(result)

if __name__ == "__main__":
    main()