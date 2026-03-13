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


# -------------------------------
# Helpers: decrypt + preprocessing
# -------------------------------
def decrypt_to_temp(encrypted_pdf: str, password: Optional[str] = None, useful_page: list[int] = [1]) -> str:
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
                    for pg in useful_page:
                        if pg-1 < len(pdf.pages):
                            new_pdf.pages.append(pdf.pages[pg-1])
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
    print(text)
    out = run_extraction(pre_processed_text, tokenizer=tokenizer, model=model)
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

if __name__ == "__main__":
    pass