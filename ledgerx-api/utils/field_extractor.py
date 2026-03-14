import json
import re
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"


def load_model(model_name: str = MODEL_NAME):
    has_cuda = torch.cuda.is_available()
    torch_dtype = torch.float16 if has_cuda else torch.float32

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        dtype=torch_dtype,
        device_map="auto",
    )
    model.eval()

    return tokenizer, model


def build_messages(ocr_text: str):
    return [
        {
            "role": "system",
            "content": (
                "You are an information extraction system for financial statements.\n"
                "Extract only values explicitly present in the OCR text.\n"
                "Do not invent, infer, calculate, or modify values.\n"
                "Return exactly one JSON object and nothing else.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract these fields:\n"
                "- statement_date\n"
                "- customer_number\n"
                "- credit_limit\n"
                "- total_amount_due\n"
                "- minimum_amount_due\n"
                "- payment_due_date\n\n"

                "Rules:\n"
                "- Map values to the headers CUSTOMER NUMBER, STATEMENT DATE, PAYMENT DUE DATE, CREDIT LIMIT, TOTAL AMOUNT DUE, and MINIMUM AMOUNT DUE.\n"
                "- Prefer values on the same line as the headers or immediately below them.\n"
                "- If values appear multiple times, choose the one nearest the header row.\n"
                "- Preserve customer_number exactly as written.\n"
                "- Normalize dates to YYYY-MM-DD when possible.\n"
                "- Money values must be JSON numbers.\n"
                "- Remove commas and currency symbols from money values.\n"
                "- Set a field to null only if that specific field is missing from the OCR text.\n"
                "- Do not output all null values if some fields are clearly present.\n"
                "- Output exactly one valid JSON object with these keys in this exact order:\n"
                '  "statement_date", "customer_number", "credit_limit", "total_amount_due", "minimum_amount_due", "payment_due_date"\n\n'

                "Example:\n"
                "OCR text:\n"
                "CUSTOMER NUMBER STATEMENT DATE PAYMENT DUE DATE CREDIT LIMIT TOTAL AMOUNT DUE MINIMUM AMOUNT DUE\n"
                "020100-4-10-7956071 JANUARY 28, 2026 FEBRUARY 18, 2026 314,000.00 20,958.15\n"
                "850.00\n\n"

                "Output:\n"
                "{\n"
                '  "statement_date": "2026-01-28",\n'
                '  "customer_number": "020100-4-10-7956071",\n'
                '  "credit_limit": 314000.0,\n'
                '  "total_amount_due": 20958.15,\n'
                '  "minimum_amount_due": 850.0,\n'
                '  "payment_due_date": "2026-02-18"\n'
                "}\n\n"

                f"OCR text:\n{ocr_text}"
            ),
        },
    ]


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        return json.loads(fenced.group(1))

    obj = re.search(r"(\{.*\})", text, flags=re.S)
    if obj:
        return json.loads(obj.group(1))

    raise ValueError(f"No valid JSON found in model output:\n{text}")


def validate_result(data: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "statement_date",
        "customer_number",
        "credit_limit",
        "total_amount_due",
        "minimum_amount_due",
        "payment_due_date",
    ]
    clean = {k: data.get(k) for k in keys}

    for key in ["credit_limit", "total_amount_due", "minimum_amount_due"]:
        val = clean.get(key)
        if isinstance(val, str):
            # keep digits and decimal point only
            val = re.sub(r"[^\d.]", "", val.strip())
            clean[key] = val or None

    for key in ["statement_date", "payment_due_date", "customer_number"]:
        val = clean.get(key)
        if isinstance(val, str):
            clean[key] = val.strip() or None

    return clean


def run_extraction(ocr_text: str, tokenizer, model) -> dict[str, Any]:
    messages = build_messages(ocr_text)

    # Apply chat template for chat-style instruction tuning
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=300,
            do_sample=False,
            temperature=0.0,
            top_p=1.0,
        )

    generated_ids = output_ids[0][inputs["input_ids"].shape[1]:]
    output_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

    parsed = extract_json(output_text)
    validated = validate_result(parsed)

    return {
        "raw_output": output_text,
        "parsed": parsed,
        "validated": validated,
    }

if __name__ == "__main__":
    # Example usage
    ocr_text = """
    Statement Date: 2024-05-01
    Customer Number: 123456789
    Credit Limit: $5,000.00
    Total Amount Due: $1,234.56
    Minimum Amount Due: $100.00
    Payment Due Date: 2024-05-31
    """
    tokenizer, model = load_model()

    result = run_extraction(ocr_text, tokenizer, model)

    print("\nRAW OUTPUT:\n")
    print(result["raw_output"])

    print("\nVALIDATED JSON:\n")
    print(json.dumps(result["validated"], indent=2, ensure_ascii=False))