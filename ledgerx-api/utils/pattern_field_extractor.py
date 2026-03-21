import re
from datetime import datetime
from typing import Dict, List, Optional
from utils.bill_utils import parse_date, parse_money


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

AMOUNT = r"(?:PHP\s*)?([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{2})|[0-9]+\.\d{2})"
DATE = r"([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{4})"
CUSTOMER_NO2 = r"(\b\d{2,}(?:-\d+){3,}\b)"

PATTERNS = {
    "total_balance": [
        rf"(?is)\btotal\s+account\s+balance\b\s*:?\s*{AMOUNT}",
        rf"(?is)\btotal\s+amount\s+due\b\s*:?\s*{AMOUNT}",
        rf"(?is)\btotal\s+amount\s+due\b[^\S\r\n]*[\r\n]+[^\S\r\n]*(?:PHP\s*)?{AMOUNT[13:-1]}",
        rf"\bTOTAL\s*AMOUNT\s*DUE\b\s*{AMOUNT[13:-1]}",
    ],

    "due_date": [
        rf"(?is)\b(?:payment\s+)?due\s+date\b\s*:?\s*{DATE}",
        rf"(?is)\bpayment\s+due\s+date\b[^\S\r\n]*[\r\n]+[^\S\r\n]*{DATE}",
        rf"(?is)\bdue\s+date\b[^\S\r\n]*[\r\n]+[^\S\r\n]*{DATE}",
        rf"\bDUE\s*DATE\b\s*({DATE_ANY})"
    ],

    "min_payment": [
        rf"(?is)\bminimum\s+payment\b\s*:?\s*{AMOUNT}",
        rf"(?is)\bminimum\s+amount\s+due\b\s*:?\s*{AMOUNT}",
        rf"(?is)\bminimum\s+amount\s+due\b[^\S\r\n]*[\r\n]+[^\S\r\n]*(?:PHP\s*)?{AMOUNT[13:-1]}",
        rf"\bMINIMUM\s*AMOUNT\s*DUE\b\s*{AMOUNT[13:-1]}",
    ],

    "credit_limit": [
        r"CREDIT\s+LIMIT[\s\S]{0,50}?(?:PHP\s*)?([\d,]+\.\d{2})",
        rf"(?is)\bcredit\s+limit\b\s*:?\s*{AMOUNT}",
        rf"(?is)\bcredit\s+limit\b[^\S\r\n]*[\r\n]+[^\S\r\n]*(?:PHP\s*)?{AMOUNT[13:-1]}",
        rf"\bCREDIT\s*LIMIT\b\s*{AMOUNT[13:-1]}",
    ],

    "statement_date": [
        rf"(?is)\bstatement\s+date\b\s*:?\s*{DATE}",
        rf"(?is)\bstatement\s+date\b[^\S\r\n]*[\r\n]+[^\S\r\n]*{DATE}",
        rf"(?is)\bcut[\s-]?off\s+date\b\s*:?\s*{DATE}",
        rf"(?is)\bstatement\s+from\b[^\n]*?\bto\b\s*({DATE})",
        rf"\bSTATEMENT\s*DATE\b\s*({DATE_ANY})"
    ],

    "customer_number": [
        rf"(?is)\bcustomer\s+number\b\s*:?\s*{CUSTOMER_NO2}",
        rf"(?is)\bcustomer\s+no\.?\b\s*:?\s*{CUSTOMER_NO2}",
        rf"(?is)\baccount\s+number\b\s*:?\s*{CUSTOMER_NO2}",
        rf"(?is)\bcard\s+number\b\s*:?\s*{CUSTOMER_NO2}",
        rf"\bCUSTOMER\s*NUMBER\b\s*{CUSTOMER_NO2}",
        
        # masked card fallback
        r"(?i)\b([0-9]{4}[-\s](?:[X\*]{4}|[0-9]{4})[-\s](?:[X\*]{4}|[0-9]{4})[-\s][0-9]{4})\b",

        rf"(?is)\bcustomer\s+number\b[^\S\r\n]*[\r\n]+[^\S\r\n]*{CUSTOMER_NO}",
    ]
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


def mask_card_number(card: str) -> str:
    """
    Masks a card number while preserving format (dashes/spaces).
    Keeps first 4 and last 4 digits visible.
    """
    if not card:
        return card

    # Extract digits only
    digits = re.sub(r"\D", "", card)

    # If too short, don't mask (avoid breaking IDs)
    if len(digits) < 12:
        return card

    # Mask middle digits
    masked_digits = digits[:4] + "X" * (len(digits) - 8) + digits[-4:]

    # Rebuild original format (preserve separators)
    result = []
    digit_idx = 0

    for ch in card:
        if ch.isdigit():
            result.append(masked_digits[digit_idx])
            digit_idx += 1
        else:
            result.append(ch)

    return "".join(result)


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
        print("Header not found (any order).")
        return None

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
                if m.lastindex:
                    value = m.group(1)
                else:
                    value = m.group(0)
                break  # stop at first valid match
        b[key] = value
        if value is None:
            none_count += 1
    
    required_fields = ["total_balance", "due_date", "min_payment"]
    
    if all(b[f] is not None for f in required_fields):
        return {
            "customer_number": mask_card_number(b.get("customer_number", None)),
            "statement_date": parse_date(b["statement_date"]) if b.get("statement_date") else None,
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
            "statement_date": parse_date(b["statement_date"]) if b.get("statement_date") else None,
            "credit_limit": parse_money(d["credit_limit"]) if d.get("credit_limit") else None,
            "total_amount_due": parse_money(d["total_due"]),
            "minimum_amount_due": parse_money(d["min_due"]),
            "payment_due_date": parse_date(d["payment_due"]),
            "source_layout": "string_table_row",
        }
    
    m = extract_after_header(text)
    if m:
        m["credit_limit"] = parse_money(m.get("credit_limit")) if m.get("credit_limit") else None
        m["total_amount_due"] = parse_money(m.get("total_amount_due"))
        m["minimum_amount_due"] = parse_money(m.get("minimum_amount_due"))
        m["payment_due_date"] = parse_date(m["payment_due_date"])
        m["statement_date"] = parse_date(m["statement_date"]) if m.get("statement_date") else None
        return m

    print("Could not match either strict sequence or table-row layout. Inspect OCR text and adjust patterns.")

    return{
        "customer_number": None,
        "statement_date": None,
        "credit_limit": None,
        "total_amount_due": None,
        "minimum_amount_due": None,
        "payment_due_date": None,
        "source_layout": None
    }


def pattern_field_extraction(ocr_text: str) -> Dict[str, Optional[str]]:
    out = extract_fields(ocr_text)
    return out