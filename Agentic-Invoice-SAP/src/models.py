"""Data models shared by every agent in the pipeline."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: Decimal = Decimal("1")
    unit_price: Decimal
    line_amount: Decimal
    material_number: Optional[str] = None
    gl_account: Optional[str] = None
    tax_code: Optional[str] = None


class ExtractedInvoice(BaseModel):
    """Schema the analyzer agent asks Claude to fill in from the PDF.

    Kept separate from `Invoice` below: this is untrusted model output and
    must pass through the validator before it is trusted with a source file
    and processing metadata attached.
    """

    vendor_name: str
    vendor_tax_id: Optional[str] = None
    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None
    currency: str = Field(min_length=3, max_length=3)
    net_amount: Decimal
    tax_amount: Decimal = Decimal("0")
    gross_amount: Decimal
    purchase_order_number: Optional[str] = None
    payment_terms: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    extraction_notes: Optional[str] = None


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    VALIDATION_FAILED = "validation_failed"
    POSTED = "posted"
    POSTING_FAILED = "posting_failed"
    DUPLICATE = "duplicate"


class Invoice(BaseModel):
    """An extracted invoice plus the processing context it carries downstream."""

    source_file: str
    company_code: str
    supplier_id: str
    extracted: ExtractedInvoice

    @property
    def invoice_number(self) -> str:
        return self.extracted.invoice_number

    @property
    def gross_amount(self) -> Decimal:
        return self.extracted.gross_amount


class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)


class SAPPostingResult(BaseModel):
    success: bool
    sap_document_number: Optional[str] = None
    fiscal_year: Optional[str] = None
    error_message: Optional[str] = None
