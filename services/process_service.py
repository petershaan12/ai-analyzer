import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

from services.pdf_service import extract_text_from_bytes
from services.ai_service import parse_invoice_text, analyse_invoice
from utils.csv_generator import rows_to_csv_string
from repositories.invoice_repository import InvoiceRepository
from models.schemas import (
    InvoiceRow,
    ParsedBilling,
    ProcessInvoiceResponse,
)

logger = logging.getLogger(__name__)

def process_invoice(
    filename: str,
    pdf_bytes: bytes,
    db: Session,
) -> ProcessInvoiceResponse:
    logger.info("=" * 60)
    logger.info("[PROCESS] Start → file=%s  size=%d bytes", filename, len(pdf_bytes))

    # 1. PDF text extraction
    raw_text = extract_text_from_bytes(pdf_bytes)
    
    # 2. AI invoice parsing
    parsed: ParsedBilling = parse_invoice_text(raw_text)

    # 3. Database query chain
    invoice_rows: list[InvoiceRow] = []
    database_total: float = 0.0

    if parsed.is_valid and parsed.billing_month and parsed.billing_year:
        category_ids = InvoiceRepository.get_vmware_category_ids(db)
        if category_ids:
            product_ids = InvoiceRepository.get_product_ids_by_categories(db, category_ids)
            invoice_rows = InvoiceRepository.get_invoice_rows_by_period(
                db,
                product_ids=product_ids,
                billing_month=parsed.billing_month,
                billing_year=parsed.billing_year,
            )
            database_total = round(sum(r.amount for r in invoice_rows), 2)
    
    # 4. Results & Analysis
    csv_content = rows_to_csv_string(invoice_rows)
    pdf_total = parsed.total_amount or 0.0
    
    month_str = parsed.billing_month or ""
    year_str = parsed.billing_year or ""
    billing_period = f"{month_str} {year_str}".strip() or "Unknown Period"
        
    analysis = None
    if parsed.is_valid:
        analysis = analyse_invoice(
            pdf_total=pdf_total,
            database_total=database_total,
            invoice_rows=invoice_rows,
            billing_period=billing_period
        )

    logger.info("[PROCESS] Done")
    logger.info("=" * 60)

    return ProcessInvoiceResponse(
        filename=filename,
        parsed_billing=parsed,
        invoice_rows=invoice_rows,
        database_total=database_total,
        csv_content=csv_content,
        csv_download_url=f"/api/v1/process/csv?filename={filename}",
        analysis=analysis,
    )
