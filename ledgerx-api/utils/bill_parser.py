from __future__ import annotations
import re, os, tempfile
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from dateutil import parser as dtparser

import pikepdf
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import pytesseract

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
                pdf.save(str(tmp_path))
        else:
            try:
                with pikepdf.open(str(src), password=password) as pdf:
                    pdf.save(str(tmp_path))
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

def pdf_text_lines(pdf_path: str, max_pages: Optional[int] = None) -> List[str]:
    """Extract text lines with PyMuPDF (selectable text)."""
    lines: List[str] = []
    with fitz.open(pdf_path) as doc:
        n = len(doc) if max_pages is None else min(max_pages, len(doc))
        for i in range(n):
            page = doc.load_page(i)
            # Use 'text' (layout-agnostic) or 'blocks' if you need coordinates
            txt = page.get_text("text")
            if txt:
                lines.extend(s for s in txt.splitlines() if s.strip())
    return lines

def ocr_text_lines(pdf_path: str, dpi: int = 300, lang: str = "eng", max_pages: Optional[int] = None) -> List[str]:
    """OCR each page (no Ghostscript needed). Requires poppler + Tesseract installed."""
    images = convert_from_path(pdf_path, dpi=dpi)
    if max_pages is not None:
        images = images[:max_pages]
    lines: List[str] = []
    for idx, img in enumerate(images, 1):
        txt = pytesseract.image_to_string(img, lang=lang)
        lines.extend(s for s in txt.splitlines() if s.strip())
    return lines

def get_text_lines_smart(encrypted_pdf: str, password: str, lang: str = "eng") -> Tuple[List[str], str]:
    """Decrypt, try PyMuPDF; if no text found, fall back to OCR."""
    dec_path = decrypt_to_temp(encrypted_pdf, password)
    lines = pdf_text_lines(dec_path)
    if not any(lines):
        # Fallback to OCR (can be slow on big PDFs; adjust dpi/lang as needed)
        lines = ocr_text_lines(dec_path, dpi=300, lang=lang)
    return lines, dec_path

# -------------------------------
# 2) Parsing logic (Due Date & Amount)
# -------------------------------
DATE_KEYWORDS = [
    r"due\s*date", r"payment\s*due", r"pay\s*by", r"statement\s*due", r"bill\s*due",
    r"payment\s*deadline", r"date\s*due"
]
AMOUNT_KEYWORDS_PRIMARY = [
    r"total\s+amount\s+due", r"amount\s+due", r"total\s+due", r"statement\s+balance",
    r"outstanding\s+balance", r"current\s+balance"
]
AMOUNT_KEYWORDS_AVOID = [
    r"minimum\s+amount\s+due", r"minimum\s+due"
]

CURRENCY_SYMS = r"(?:₱|\bPHP\b|(?<!\S)Php)"
AMOUNT_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?"
AMOUNT_RX = re.compile(rf"{CURRENCY_SYMS}?\s*({AMOUNT_NUM})", re.IGNORECASE)

def normalize_amount(s: str) -> Optional[float]:
    m = AMOUNT_RX.search(s)
    if not m:
        return None
    num = m.group(1).replace(",", "")
    try:
        return float(num)
    except ValueError:
        return None

def parse_date_any(s: str) -> Optional[str]:
    """Return ISO date (YYYY-MM-DD) if parsable."""
    s = s.strip()
    # Try several liberal parses (handles 'Oct 15, 2025', '15 Oct 2025', '10/15/2025')
    for dayfirst in (False, True):
        try:
            dt = dtparser.parse(s, dayfirst=dayfirst, fuzzy=True, yearfirst=False)
            return dt.date().isoformat()
        except Exception:
            continue
    return None

def find_nearby(lines: List[str], idx: int, window: int = 2) -> List[str]:
    L = max(0, idx - window)
    R = min(len(lines), idx + window + 1)
    return lines[L:R]

def match_any(line: str, patterns: List[str]) -> Optional[re.Match]:
    for pat in patterns:
        m = re.search(pat, line, flags=re.IGNORECASE)
        if m:
            return m
    return None

def extract_due_and_amount(lines: List[str]) -> Dict[str, Optional[str]]:
    """
    Strategy:
      - For due date: look for date keywords; parse date on the same line or the next 2 lines.
      - For amount: prioritize PRIMARY keywords; avoid 'Minimum Amount Due' if a better one exists.
      - If conflicting amounts exist, prefer the one nearest to a primary keyword.
    """
    due_date_iso: Optional[str] = None
    amount_value: Optional[float] = None
    amount_source: Optional[str] = None

    # Pass 1: Due Date
    for i, line in enumerate(lines):
        if match_any(line, DATE_KEYWORDS):
            # Try same line first
            dd = parse_date_any(line)
            if dd:
                due_date_iso = dd
                break
            # Try next lines (within small window)
            for ctx in find_nearby(lines, i, window=2):
                if ctx == line:
                    continue
                dd = parse_date_any(ctx)
                if dd:
                    due_date_iso = dd
                    break
            if due_date_iso:
                break

    # Pass 2: Amounts - collect candidates with simple scoring
    candidates: List[Tuple[float, int, str]] = []  # (amount, score, context)
    for i, line in enumerate(lines):
        # Skip minimum due if possible
        if match_any(line, AMOUNT_KEYWORDS_AVOID):
            am = normalize_amount(line)
            if am is not None:
                # Lower score for minimum due
                candidates.append((am, 1, line))
            continue

        pri_hit = match_any(line, AMOUNT_KEYWORDS_PRIMARY)
        am = normalize_amount(line)
        if am is not None:
            score = 3 if pri_hit else 2
            # small bonus if currency symbol present
            if re.search(CURRENCY_SYMS, line, flags=re.IGNORECASE):
                score += 1
            candidates.append((am, score, line))

        # Look-ahead: amount on next line after a primary keyword
        if pri_hit and i + 1 < len(lines):
            am2 = normalize_amount(lines[i + 1])
            if am2 is not None:
                candidates.append((am2, 4, lines[i] + " | " + lines[i + 1]))

    if candidates:
        # Pick highest score; if tie, pick the largest amount (credit card/utility “Total Due” is usually max)
        candidates.sort(key=lambda t: (t[1], t[0]), reverse=True)
        amount_value, _, amount_source = candidates[0]

    return {
        "due_date": due_date_iso,                          # e.g., "2025-10-15"
        "amount": f"{amount_value:.2f}" if amount_value is not None else None,  # stringified amount
        "amount_context": amount_source                    # the line where we found it (useful for debugging)
    }

# -------------------------------
# 3) One-call entry point
# -------------------------------
def extract_bill_fields(encrypted_pdf: str, password: str, lang: str = "eng") -> Dict[str, Optional[str]]:
    lines, dec_path = get_text_lines_smart(encrypted_pdf, password, lang=lang)
    out = extract_due_and_amount(lines)
    # Clean up decrypted temp file
    try:
        os.remove(dec_path)
    except Exception:
        pass
    return out

def main():
    result = extract_bill_fields("./gmail_attachments_poc/20250914.pdf", password="20Oct1997814614", lang="eng")
    print(result)

if __name__ == "__main__":
    main()