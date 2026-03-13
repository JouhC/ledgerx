import json
import re
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "Qwen/Qwen2.5-3B-Instruct"


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
                "You are an information extraction model for financial statements. "
                "Extract only values that are explicitly present in the OCR text. "
                "Do not invent values. "
                "If a field is missing or unreadable, return null. "
                "Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract these fields from the OCR text and return JSON only:\n"
                "{\n"
                '  "statement_date": null,\n'
                '  "customer_number": null,\n'
                '  "credit_limit": null,\n'
                '  "total_amount_due": null,\n'
                '  "minimum_amount_due": null,\n'
                '  "payment_due_date": null\n'
                "}\n\n"
                "Rules:\n"
                "- Preserve customer_number exactly as seen.\n"
                "- Normalize dates to YYYY-MM-DD when possible.\n"
                "- Normalize amounts to plain numbers without currency symbols or commas when possible.\n"
                "- Return valid JSON only.\n\n"
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
            max_new_tokens=256,
            do_sample=False,
            temperature=None,
            top_p=None,
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