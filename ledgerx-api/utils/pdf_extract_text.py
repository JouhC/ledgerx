import io
import re
import string
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageFilter, ImageOps
import pymupdf

def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    img = image.convert("L")  # grayscale
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)

    # simple threshold
    img = img.point(lambda p: 255 if p > 180 else 0)
    return img

def extract_text_from_page(page: fitz.Page) -> str:
    return page.get_text("text").strip()

def render_page_to_pil(page: fitz.Page, dpi: int = 200) -> Image.Image:
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def ocr_page(image: Image.Image, lang: str = "eng", psm: int = 0) -> str:
    config = f"--psm {psm}"
    text = pytesseract.image_to_string(image, lang=lang, config=config)
    return text.strip()


def is_text_sufficient(text: str, min_chars: int = 50) -> bool:
    if not text:
        return False

    text = text.strip()

    # 1. Length check (basic)
    if len(text) < min_chars:
        return False

    # 2. Remove whitespace
    text_no_space = re.sub(r"\s+", "", text)

    # 3. Ratio of printable ASCII chars
    printable_ratio = sum(c in string.printable for c in text_no_space) / max(len(text_no_space), 1)

    # 4. Ratio of alphabetic chars
    alpha_ratio = sum(c.isalpha() for c in text_no_space) / max(len(text_no_space), 1)

    # 5. Detect "word-like" tokens (at least 3 letters)
    words = re.findall(r"[A-Za-z]{3,}", text)
    word_count = len(words)

    # ---- thresholds (tunable) ----
    if printable_ratio < 0.7:
        return False

    if alpha_ratio < 0.3:
        return False

    if word_count < 5:
        return False

    return True


def normalize_whitespace(text: str) -> str:
    text = text.replace("\x0c", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def run_ocr(
    page,
    ocr_lang: str = "eng",
    ocr_psm: int = 4,
    dpi: int = 200,
    )-> str:

    image = render_page_to_pil(page, dpi=dpi)
    image = preprocess_image_for_ocr(image)
    ocr_text = ocr_page(image, lang=ocr_lang, psm=ocr_psm)

    return ocr_text


def get_text_from_pdf(
        pdf_path: str,
        lang: str = "eng",
        ocr_psm: int = 4,
        dpi: int = 200,
        fallback: bool = False) -> str:
    """
    Extract text from a PDF using Native and Tesseract OCR when needed.
    """
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    
    if fallback:
        text = run_ocr(page, lang, ocr_psm, dpi)
        return text

    text = extract_text_from_page(page)
    return normalize_whitespace(text)