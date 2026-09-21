from datetime import date
from decimal import Decimal

import pytest

from src.agents.validator_agent import InvoiceValidatorAgent
from src.models import ExtractedInvoice, LineItem, ProcessingStatus
from src.storage import InvoiceLedger


@pytest.fixture
def ledger(tmp_path) -> InvoiceLedger:
    return InvoiceLedger(str(tmp_path / "ledger.sqlite3"))


def _extracted(**overrides) -> ExtractedInvoice:
    defaults = dict(
        vendor_name="Acme Supplies GmbH",
        invoice_number="INV-1001",
        invoice_date=date(2026, 1, 15),
        currency="EUR",
        net_amount=Decimal("100.00"),
        tax_amount=Decimal("19.00"),
        gross_amount=Decimal("119.00"),
        line_items=[],
    )
    defaults.update(overrides)
    return ExtractedInvoice(**defaults)


def test_valid_invoice_passes(ledger):
    validator = InvoiceValidatorAgent(ledger)
    result = validator.validate(_extracted(), supplier_id="VENDOR-42")
    assert result.is_valid
    assert result.errors == []


def test_amount_mismatch_is_rejected(ledger):
    validator = InvoiceValidatorAgent(ledger)
    result = validator.validate(_extracted(gross_amount=Decimal("500.00")), supplier_id="VENDOR-42")
    assert not result.is_valid
    assert any("gross_amount" in e for e in result.errors)


def test_line_items_must_reconcile_with_net_amount(ledger):
    extracted = _extracted(
        line_items=[
            LineItem(description="Widgets", quantity=Decimal("1"), unit_price=Decimal("10"), line_amount=Decimal("10.00")),
        ]
    )
    validator = InvoiceValidatorAgent(ledger)
    result = validator.validate(extracted, supplier_id="VENDOR-42")
    assert not result.is_valid
    assert any("line items" in e for e in result.errors)


def test_duplicate_invoice_is_rejected(ledger):
    ledger.record(
        "prior.pdf",
        ProcessingStatus.POSTED,
        supplier_id="VENDOR-42",
        invoice_number="INV-1001",
        sap_document_number="5100000123",
    )
    validator = InvoiceValidatorAgent(ledger)
    result = validator.validate(_extracted(), supplier_id="VENDOR-42")
    assert not result.is_valid
    assert any("already posted" in e for e in result.errors)


def test_missing_required_fields_are_rejected(ledger):
    validator = InvoiceValidatorAgent(ledger)
    result = validator.validate(_extracted(invoice_number="  ", vendor_name=""), supplier_id="VENDOR-42")
    assert not result.is_valid
    assert any("invoice_number" in e for e in result.errors)
    assert any("vendor_name" in e for e in result.errors)
