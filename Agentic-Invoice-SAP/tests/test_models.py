from datetime import date
from decimal import Decimal

from src.models import ExtractedInvoice, Invoice, LineItem


def _sample_extracted(**overrides) -> ExtractedInvoice:
    defaults = dict(
        vendor_name="Acme Supplies GmbH",
        invoice_number="INV-1001",
        invoice_date=date(2026, 1, 15),
        currency="EUR",
        net_amount=Decimal("100.00"),
        tax_amount=Decimal("19.00"),
        gross_amount=Decimal("119.00"),
        line_items=[
            LineItem(description="Widgets", quantity=Decimal("10"), unit_price=Decimal("10.00"), line_amount=Decimal("100.00")),
        ],
    )
    defaults.update(overrides)
    return ExtractedInvoice(**defaults)


def test_extracted_invoice_round_trip():
    extracted = _sample_extracted()
    assert extracted.gross_amount == Decimal("119.00")
    assert len(extracted.line_items) == 1


def test_invoice_exposes_convenience_properties():
    extracted = _sample_extracted()
    invoice = Invoice(
        source_file="/data/inbox/inv-1001.pdf",
        company_code="1000",
        supplier_id="VENDOR-42",
        extracted=extracted,
    )
    assert invoice.invoice_number == "INV-1001"
    assert invoice.gross_amount == Decimal("119.00")
