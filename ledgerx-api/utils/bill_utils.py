from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation
import unicodedata
from datetime import datetime
import re
from zoneinfo import ZoneInfo

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


def get_ph_time(from_datatime: str = None):
    if from_datatime:
        dt = datetime.fromisoformat(from_datatime)
        return dt.astimezone(ZoneInfo("Asia/Manila"))
    
    ph_time = datetime.now(ZoneInfo("Asia/Manila"))
    return ph_time
    