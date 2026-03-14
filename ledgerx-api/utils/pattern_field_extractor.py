import re
from datetime import datetime
from typing import Dict, List, Optional
from utils.bill_preprocessing import parse_date, parse_money, decrypt_to_temp, get_text_from_pdf
import shutil


HEADER_ANY_ORDER = re.compile(
    r"""(?i)(?=.*\bCUSTOMER\s+NUMBER\b)(?=.*\bSTATEMENT\s+DATE\b)(?=.*\bCREDIT\s+LIMIT\b)(?=.*\bTOTAL\s+AMOUNT\s+DUE\b)(?=.*\bMINIMUM\s+AMOUNT\s+DUE\b)(?=.*\bPAYMENT\s+DUE\s+DATE\b)"""
)

CUSTOMER_NO   = re.compile(r"\b\d{2,}(?:-\d+){3,}\b")
MONEY_STRICT  = re.compile(r"(?<![\dA-Za-z])(?:\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+\.\d{2})(?![\dA-Za-z])")
DATE_CAND     = re.compile(r"""(?ix)
    (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|
       June|July|August|September|October|November|December)
    [\s\-]+\d{1,2},?[\s\-]+\d{4}
    |
    \d{1,2}[\s\-]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\-]+\d{4}
""")

MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_LONG = rf"{MONTH}\s+\d{{1,2}},\s+\d{{4}}"   # e.g., August 28, 2025
DATE_DMY  = r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}"  # 06 Oct 2025
DATE_ANY  = rf"(?:{DATE_LONG}|{DATE_DMY})"

DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %b %Y", "%d-%b-%Y", "%B %d %Y", "%b %d %Y")

PATTERNS = {
    "total_balance": [
        r"(?i)total\s+account\s+balance\s+([\d,]+\.\d{2})",
        r"TOTAL AMOUNT DUE[\sA-Z]*([0-9][0-9,]*\.\d{2})"],
    "due_date": [
        r"(?i)(?:payment\s+)?due\s+date\s+(\d{1,2}\s+\w+\s+\d{4})",
        r"PAYMENT\s+DUE\s+DATE\b[^\n\r]*[\r\n]+([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{4})"],
    "min_payment": [
        r"(?i)minimum\s+payment\s+([\d,]+\.\d{2})",
        r"MINIMUM AMOUNT DUE[\sA-Z]*([0-9][0-9,]*\.\d{2})"],
    "credit_limit": [
        r"CREDIT\s+LIMIT[\s\S]{0,50}?PHP[\s\S]{0,20}?([0-9][0-9,]*\.\d{2})",
    ],
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

def parse_date_safe(s: str) -> Optional[datetime]:
    s = re.sub(r"\s+", " ", s.strip().replace("Sept", "Sep"))
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def extract_after_header(text: str, max_lines: int = 12) -> Dict[str, str]:
    lines = text.splitlines()

    # 1) find header
    hdr_idx = None
    for i, ln in enumerate(lines):
        if HEADER_ANY_ORDER.match(" ".join(ln.strip().split())):
            hdr_idx = i
            break
    if hdr_idx is None:
        raise ValueError("Header not found (any order).")

    # 2) collect a generous block AFTER header (do NOT stop on blank lines)
    stop_markers = ("| Previous", "## ")
    block: List[str] = []
    for ln in lines[hdr_idx + 1 :]:
        if any(ln.strip().startswith(m) for m in stop_markers):
            break
        block.append(ln)                 # include blanks; we’ll normalize later
        if len(block) >= max_lines:      # sanity cap
            break

    # Normalize whitespace
    blob = " ".join(seg.strip() for seg in block if seg is not None)
    blob = re.sub(r"\s{2,}", " ", blob).strip()

    # 3) customer number
    cm = CUSTOMER_NO.search(blob)
    customer_number = cm.group(0) if cm else ""

    # 4) dates → chronological: first = statement_date, last = payment_due
    date_strs = [m.group(0) for m in DATE_CAND.finditer(blob)]
    parsed = [(ds, parse_date_safe(ds)) for ds in date_strs]
    parsed = [(ds, dt) for ds, dt in parsed if dt]
    seen = set()
    uniq = []
    for ds, dt in parsed:
        key = (dt.year, dt.month, dt.day)
        if key not in seen:
            seen.add(key)
            uniq.append((ds, dt))
    uniq.sort(key=lambda x: x[1])
    statement_date = uniq[0][0] if uniq else ""
    payment_due    = uniq[-1][0] if len(uniq) >= 2 else ""

    # 5) money: search AFTER the customer number; if fewer than 3 amounts, widen window
    search_text = blob[cm.end():] if cm else blob
    money_vals = [m.group(0) for m in MONEY_STRICT.finditer(search_text)]

    # Fallback: if <3 found, search the whole post-header block
    if len(set(money_vals)) < 3:
        money_vals = [m.group(0) for m in MONEY_STRICT.finditer(blob)]

    # Take first 3 distinct tokens in encounter order
    distinct = []
    seen_m = set()
    for m in money_vals:
        if m not in seen_m:
            seen_m.add(m)
            distinct.append(m)
        if len(distinct) == 3:
            break

    def m2f(s: str) -> float:
        return float(s.replace(",", ""))

    credit_limit = total_due = min_due = ""
    if len(distinct) == 3:
        lo, mid, hi = sorted(distinct, key=m2f)
        min_due, total_due, credit_limit = lo, mid, hi
    else:
        vals_sorted = sorted(distinct, key=m2f) if distinct else []
        if vals_sorted:
            min_due = vals_sorted[0]
            credit_limit = vals_sorted[-1]
            if len(vals_sorted) >= 2:
                total_due = vals_sorted[-2]

    if payment_due or total_due:
        return {
            "customer_number": customer_number,
            "statement_date": statement_date,
            "payment_due_date": payment_due,
            "credit_limit": credit_limit,
            "total_amount_due": total_due,
            "minimum_amount_due": min_due,
            "source_layout": "table_row"
        }
    return None


def extract_fields(text: str) -> dict:
    # First try the brute-force method
    b = {}
    none_count = 0
    
    for key, patterns in PATTERNS.items():
        value = None
        # Try each pattern until something matches
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if m:
                value = m.group(1)
                break  # stop at first valid match
        b[key] = value
        if value is None:
            none_count += 1
    
    required_fields = ["total_balance", "due_date", "min_payment"]
    
    if all(b[f] is not None for f in required_fields):
        return {
            "customer_number": None,  # not present in this layout
            "statement_date": None,   # not present in this layout
            "credit_limit": parse_money(b["credit_limit"]) if b.get("credit_limit") else None,
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


def pattern_extract_bill_fields(encrypted_pdf: str, password: str, lang: str = "eng") -> Dict[str, Optional[str]]:
    dec_path = decrypt_to_temp(encrypted_pdf, password)
    text = get_text_from_pdf(dec_path, lang=lang)
    print(text)
    out = extract_fields(text)
    print(out)
    # Clean up decrypted temp file
    try:
        shutil.move(dec_path, encrypted_pdf)
        # Ensure tempfile is gone
        if dec_path.exists():
            dec_path.unlink(missing_ok=True)
    except Exception:
        pass
    return out