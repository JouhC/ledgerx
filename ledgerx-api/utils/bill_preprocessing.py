from __future__ import annotations
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
from utils.field_extractor import run_extraction
from utils.pattern_field_extractor import pattern_field_extraction
from utils.deterministic_validator import deterministic_validator
from utils.bill_utils import parse_date, parse_money
from utils.password_crypto import decrypt_password
from pathlib import Path
from typing import Any, Dict, List, Optional
import html
import pikepdf
import re
import tempfile
from pathlib import Path
from typing import Optional, Sequence
import tempfile
import pikepdf


# -------------------------------
# Helpers: decrypt + preprocessing
# -------------------------------

def decrypt_to_temp(value: Dict[str, Any]) -> str:
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
    src = Path(value['bills_path'])
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    try:
        open_kwargs = {"password": decrypt_password(value.get('encrypted_password'))} if value.get('encrypted_password') is not None else {}

        with pikepdf.open(str(src), **open_kwargs) as pdf:
            new_pdf = pikepdf.Pdf.new()

            if value.get('name') == "BPI Rewards" and len(pdf.pages) >= 6:
                pages_to_extract = [3] 
            else:
                pages_to_extract = list(value['useful_page']) if value.get('useful_page') is not None else [1]
            print("Pages to extract:", pages_to_extract)
            print(f"PDF has {len(pdf.pages)} page(s). Extracting pages: {pages_to_extract}")

            if not all(isinstance(pg, int) and pg >= 1 for pg in pages_to_extract):
                raise ValueError("All page numbers in useful_page must be positive integers.")

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
        if value.get('encrypted_password') is None:
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
    text = raw_text or ""

    # 1) HTML unescape
    text = html.unescape(text)

    # 2) Remove markdown image placeholders
    text = re.sub(r"<!--\s*image\s*-->", " ", text, flags=re.I)

    # 3) Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 4) Remove markdown table separator lines only
    text = re.sub(r"^\|[-:\s|]+\|?$", " ", text, flags=re.M)

    # 5) Collapse horizontal whitespace, but preserve line breaks
    text = re.sub(r"[ \t]+", " ", text)

    # 6) Strip each line, but keep line structure
    lines = [line.strip() for line in text.split("\n")]

    # 7) Remove only fully empty runs
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _wrapper_field_extraction(ocr_text: str, tokenizer: Any, model: Any) -> Dict[str, Optional[str]]:
    out = run_extraction(ocr_text, tokenizer=tokenizer, model=model)
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

    return validated


def extract_bill_fields(
    value: Dict[str, Any],
    required_fields: List[str],
    lang: str = "eng",
    model: Optional[Any] = None,
    tokenizer: Optional[Any] = None,
    debug: bool = False,
) -> Dict[str, Any]:

    dec_path = None

    try:
        dec_path = Path(decrypt_to_temp(value))

        text = get_text_from_pdf(str(dec_path), lang=lang)
        pre_processed_text = preprocess_statement_text(text)

        if debug:
            print(pre_processed_text)


        pattern_output = pattern_field_extraction(pre_processed_text)
        
        if tokenizer is not None and model is not None:
            slm_output = _wrapper_field_extraction(
                pre_processed_text,
                tokenizer=tokenizer,
                model=model
            )

            final_output = deterministic_validator(slm_output, pattern_output, required_fields)
            return final_output, dec_path
        
        return pattern_output, dec_path
    
    except Exception as e:
        print(f"Error in extract_bill_fields: {e}")
        raise

if __name__ == "__main__":
    pass