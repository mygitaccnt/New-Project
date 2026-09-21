from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.agents.sap_posting_agent import SAPPostingAgent, build_supplier_invoice_payload
from src.models import ExtractedInvoice, Invoice, LineItem
from src.sap_client import SAPCredentials, SAPODataClient, SAPPostingError


def _invoice(**overrides) -> Invoice:
    extracted_defaults = dict(
        vendor_name="Acme Supplies GmbH",
        invoice_number="INV-1001",
        invoice_date=date(2026, 1, 15),
        currency="EUR",
        net_amount=Decimal("100.00"),
        tax_amount=Decimal("19.00"),
        gross_amount=Decimal("119.00"),
        line_items=[
            LineItem(description="Widgets", quantity=Decimal("10"), unit_price=Decimal("10.00"), line_amount=Decimal("100.00"), tax_code="V1"),
        ],
    )
    extracted_defaults.update(overrides.pop("extracted_overrides", {}))
    return Invoice(
        source_file="/data/inbox/inv-1001.pdf",
        company_code="1000",
        supplier_id="VENDOR-42",
        extracted=ExtractedInvoice(**extracted_defaults),
        **overrides,
    )


def test_payload_uses_gl_account_when_no_po():
    payload = build_supplier_invoice_payload(_invoice(), gl_account_fallback="0000400000")
    assert payload["CompanyCode"] == "1000"
    assert payload["InvoicingParty"] == "VENDOR-42"
    assert payload["SupplierInvoiceIDByInvcgParty"] == "INV-1001"
    item = payload["to_SupplierInvoiceItem"][0]
    assert item["GLAccount"] == "0000400000"
    assert "PurchaseOrder" not in item


def test_payload_uses_po_reference_when_present():
    invoice = _invoice(extracted_overrides={"purchase_order_number": "4500001234"})
    payload = build_supplier_invoice_payload(invoice, gl_account_fallback="0000400000")
    item = payload["to_SupplierInvoiceItem"][0]
    assert item["PurchaseOrder"] == "4500001234"
    assert "GLAccount" not in item


def test_sap_client_raises_with_sap_error_message():
    session = MagicMock()
    session.get.return_value = MagicMock(headers={"X-CSRF-Token": "abc123"})
    error_response = MagicMock(status_code=400)
    error_response.json.return_value = {"error": {"message": {"value": "Company code 1000 does not exist"}}}
    session.post.return_value = error_response

    client = SAPODataClient(
        SAPCredentials(base_url="https://s4.example.com", username="u", password="p", client="100"),
        session=session,
    )

    with pytest.raises(SAPPostingError, match="Company code 1000 does not exist"):
        client.create_supplier_invoice({"CompanyCode": "1000"})


def test_sap_posting_agent_reports_failure_without_raising():
    session = MagicMock()
    session.get.return_value = MagicMock(headers={"X-CSRF-Token": "abc123"})
    error_response = MagicMock(status_code=400)
    error_response.json.return_value = {"error": {"message": {"value": "Duplicate invoice"}}}
    session.post.return_value = error_response

    client = SAPODataClient(
        SAPCredentials(base_url="https://s4.example.com", username="u", password="p", client="100"),
        session=session,
    )
    agent = SAPPostingAgent(client, gl_account_fallback="0000400000")

    result = agent.post(_invoice())

    assert result.success is False
    assert result.error_message == "Duplicate invoice"
