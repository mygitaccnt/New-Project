"""Deterministic business-rule checks the LLM extraction has to pass before
anything gets anywhere near SAP. No model call happens here on purpose.
"""
from __future__ import annotations

from decimal import Decimal

from ..models import ExtractedInvoice, ValidationResult
from ..storage import InvoiceLedger

_AMOUNT_TOLERANCE = Decimal("0.05")


class InvoiceValidatorAgent:
    def __init__(self, ledger: InvoiceLedger) -> None:
        self._ledger = ledger

    def validate(self, extracted: ExtractedInvoice, supplier_id: str) -> ValidationResult:
        errors: list[str] = []

        if not extracted.invoice_number.strip():
            errors.append("invoice_number is missing")
        if not extracted.vendor_name.strip():
            errors.append("vendor_name is missing")
        if extracted.gross_amount <= 0:
            errors.append(f"gross_amount must be positive, got {extracted.gross_amount}")

        expected_gross = extracted.net_amount + extracted.tax_amount
        if abs(expected_gross - extracted.gross_amount) > _AMOUNT_TOLERANCE:
            errors.append(
                f"net_amount ({extracted.net_amount}) + tax_amount ({extracted.tax_amount}) "
                f"= {expected_gross}, which does not match gross_amount ({extracted.gross_amount})"
            )

        if extracted.line_items:
            line_item_total = sum((item.line_amount for item in extracted.line_items), Decimal("0"))
            if abs(line_item_total - extracted.net_amount) > _AMOUNT_TOLERANCE:
                errors.append(
                    f"line items sum to {line_item_total}, which does not match net_amount "
                    f"({extracted.net_amount})"
                )

        if extracted.invoice_number.strip() and self._ledger.is_duplicate(supplier_id, extracted.invoice_number):
            errors.append(
                f"invoice {extracted.invoice_number} from supplier {supplier_id} was already posted"
            )

        return ValidationResult(is_valid=not errors, errors=errors)
