from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class ParsedBilling(BaseModel):
    is_valid: bool = Field(True, description="Whether the document is a valid invoice")
    validation_reason: Optional[str] = Field(None, description="Reason if document is invalid")
    billing_month: Optional[str] = Field(None, description="Format: YYYY-MM")
    billing_year: Optional[str] = Field(None, description="Format: YYYY")
    total_amount: Optional[float] = Field(None, description="Numeric, no currency symbol")
    currency: Optional[str] = None

class InvoiceRow(BaseModel):
    customer_id: str   = Field(description="From invoices table")
    name:        str   = Field(description="From customers table via customer_id")
    code:        str   = Field(description="From products table")
    itemname:    str   = Field(description="From products table")
    amount:      float = Field(description="From invoice_items.amount — BEFORE PPN")

class ReconciliationStatus(str, Enum):
    MATCH     = "MATCH"
    NOT_MATCH = "NOT_MATCH"

class AnalysisResult(BaseModel):
    pdf_total:          float
    database_total:     float
    difference:         float
    status:             ReconciliationStatus
    risk_level:         str  = Field(description="LOW / MEDIUM / HIGH")
    analysis:           str  = Field(description="Professional markdown commentary (No tables)")
    email_summary:      str  = Field(description="Concise executive summary")
    customer_breakdown: List[dict] = Field(default_factory=list, description="Structured customer data")
    product_breakdown:  List[dict] = Field(default_factory=list, description="Structured product data")
    recommendations:    List[dict] = Field(default_factory=list, description="Structured recommendations")
    note:               str  = Field(
        default="All amounts are BEFORE PPN (VAT excluded)",
        description="Always present as audit trail"
    )

class ProcessInvoiceResponse(BaseModel):
    filename: str
    parsed_billing: ParsedBilling
    invoice_rows: List[InvoiceRow]
    database_total: float = Field(description="Sum of all amounts, BEFORE PPN")
    csv_content: str = Field(description="Full CSV text, ready to attach")
    csv_download_url: str
    analysis: Optional[AnalysisResult] = None
    message: str = "Invoice processed successfully"
