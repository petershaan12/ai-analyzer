import json
import re
import logging
from typing import Any
from openai import OpenAI
from core.config import get_settings
from models.schemas import ParsedBilling, AnalysisResult, ReconciliationStatus

logger = logging.getLogger(__name__)
settings = get_settings()

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        logger.info("[AI] Initialising Qwen client → %s", settings.ai_base_url)
        logger.info("[AI] API Key: %s", settings.ai_api_key)
        _client = OpenAI(
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
        )
    return _client


def _chat(system: str, user: str) -> str:
    logger.debug("[AI] Sending request to model: %s", settings.ai_model)
    response = _get_client().chat.completions.create(
        model=settings.ai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.0,  # deterministic – no hallucinations
        max_tokens=512,
    )
    content = response.choices[0].message.content or ""
    logger.debug("[AI] Raw response: %s", content[:200])
    return content


def _extract_json(raw: str) -> dict[str, Any]:
    """Strip markdown fences then parse first JSON object found."""
    # Remove markers
    clean = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    
    # Try to find the first '{' and the last '}'
    start = clean.find('{')
    end = clean.rfind('}')
    
    if start == -1 or end == -1 or end < start:
         # Fallback to current regex if manual find fails
         match = re.search(r"\{.*\}", clean, re.DOTALL)
         if not match:
             raise ValueError(f"No JSON object found in AI reply:\n{raw}")
         json_str = match.group()
    else:
        json_str = clean[start:end+1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error: {str(e)} | Raw: {raw[:200]}...")
        # If it's just a missing bracket at the very end, try to fix it
        if not json_str.endswith('}'):
            try:
                return json.loads(json_str + '"}') # Very basic attempt to close string and object
            except:
                pass
        raise ValueError(f"Failed to parse AI JSON response: {str(e)}\nReply:\n{raw}")


# ═════════════════════════════════════════════════════════════════════════════
# PROMPT 1 – Parse PDF invoice → billing metadata
# ═════════════════════════════════════════════════════════════════════════════

_PARSE_SYSTEM = """You are a financial document parser AI.
Your task: extract billing metadata from raw invoice text.
Return ONLY valid JSON — no explanation, no markdown fences.

Extract:
  is_valid      : boolean. Set to false if text is NOT an invoice or is inappropriate/pornographic.
  validation_reason : string. If is_valid is false, explain why in Indonesian.
  billing_month : format YYYY-MM  (convert text months like "January 2025" → "2025-01")
  billing_year  : format YYYY
  total_amount  : numeric only, no currency symbol, no thousand separator
  currency      : e.g. IDR, USD — null if not found

Rules:
- If multiple totals exist, pick the FINAL GRAND TOTAL.
- Do NOT hallucinate. If a field is missing, return null.

Return ONLY this JSON:
{
  "is_valid": true,
  "validation_reason": null,
  "billing_month": null,
  "billing_year": null,
  "total_amount": null,
  "currency": null
}"""


def parse_invoice_text(invoice_text: str) -> ParsedBilling:
    """
    Send pdfplumber-extracted text to Qwen.
    Returns a ParsedBilling with month, year, total, currency.
    """
    logger.info("[AI:parse] Parsing invoice text (%d chars)", len(invoice_text))
    user_msg = f'Invoice text:\n"""\n{invoice_text}\n"""'
    raw = _chat(_PARSE_SYSTEM, user_msg)
    data = _extract_json(raw)

    # Coerce total_amount to float
    raw_amount = data.get("total_amount")
    if raw_amount:
        try:
            data["total_amount"] = float(str(raw_amount).replace(",", ""))
        except ValueError:
            data["total_amount"] = None

    logger.info(
        "[AI:parse] Result → month=%s year=%s total=%s",
        data.get("billing_month"),
        data.get("billing_year"),
        data.get("total_amount"),
    )
    return ParsedBilling(**data)


_ANALYSIS_SYSTEM = """You are a professional Financial Auditor AI.
All amounts are BEFORE PPN (VAT excluded).

### OUTPUT REQUIREMENTS:
Return ONLY a valid JSON object:
1. "pdf_total": float
2. "database_total": float
3. "status": "MATCH" or "NOT_MATCH"
4. "risk_level": "LOW", "MEDIUM", or "HIGH"
5. "analysis": Professional markdown commentary (NO TABLES, NO BREAKDOWNS here).
6. "email_summary": A concise executive summary.
7. "customer_breakdown": List of objects: {"no": int, "customer": str, "amount": float, "percentage": str}
8. "product_breakdown": List of objects: {"kode": str, "produk": str, "amount": float, "percentage": str}
9. "recommendations": List of objects: {"issue": str, "recommendation": str}

### RULES:
- Language: Indonesian.
- Currency: Rp #.###.###.
- **NO MARKDOWN TABLES**. Provide raw data in the JSON fields instead for system rendering.
- Return ONLY JSON. No markdown fences."""


def analyse_invoice(
    pdf_total: float, 
    database_total: float,
    invoice_rows: list[Any] = None,
    billing_period: str = "Unknown"
) -> AnalysisResult:
    """
    Ask Qwen to compare PDF total vs database total and generate markdown analysis.
    Always enforces the before-PPN rule.
    """
    if invoice_rows is None:
        invoice_rows = []

    # Summarize customer and product data to save LLM tokens and computation
    customers = {}
    products = {}
    for r in invoice_rows:
        customers[r.name] = customers.get(r.name, 0) + r.amount
        prod_key = f"{r.code}__{r.itemname}"
        products[prod_key] = products.get(prod_key, 0) + r.amount

    cust_sorted = sorted(customers.items(), key=lambda x: x[1], reverse=True)
    prod_sorted = sorted(products.items(), key=lambda x: x[1], reverse=True)

    logger.info(
        "[AI:analyse] pdf_total=%.2f  database_total=%.2f",
        pdf_total,
        database_total,
    )
    user_msg = json.dumps({
        "billing_period": billing_period,
        "pdf_total": pdf_total,
        "database_total": database_total,
        "customer_breakdown": [{"customer": k, "amount": v} for k, v in cust_sorted],
        "product_breakdown": [{"code": k.split("__")[0], "product": k.split("__")[1], "amount": v} for k, v in prod_sorted]
    }, indent=2)

    # Use larger text capacity since output might be long
    # We increase max_tokens so the markdown isn't abruptly cut off
    logger.debug("[AI] Sending request to model: %s", settings.ai_model)
    response = _get_client().chat.completions.create(
        model=settings.ai_model,
        messages=[
            {"role": "system", "content": _ANALYSIS_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content or ""
    logger.debug("[AI] Raw response: %s", raw[:200])
    
    data = _extract_json(raw)

    # Coerce and calculate locally to save AI tokens and ensure accuracy
    data["pdf_total"] = float(data.get("pdf_total", pdf_total))
    data["database_total"] = float(data.get("database_total", database_total))
    data["difference"] = data["database_total"] - data["pdf_total"]

    if "status" not in data:
        data["status"] = "MATCH" if data["difference"] == 0 else "NOT_MATCH"
        
    data["status"] = ReconciliationStatus(data.get("status", "NOT_MATCH"))

    logger.info(
        "[AI:analyse] status=%s  risk=%s  diff=%.2f",
        data["status"],
        data.get("risk_level"),
        data["difference"],
    )
    return AnalysisResult(**data)
