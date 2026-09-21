"""Maps a validated Invoice onto the API_SUPPLIERINVOICE_PROCESS_SRV payload
shape and posts it through SAPODataClient.

The header/item field names below match SAP's public API
(https://api.sap.com/api/API_SUPPLIERINVOICE_PROCESS_SRV) for the
A_SupplierInvoice / A_SupplierInvoiceItem entities. What every real
deployment has to customize is the *mapping*: which GL account or PO an
extracted line item posts against is chart-of-accounts- and
procurement-process-specific, so `gl_account_fallback` is the one thing
this agent takes from outside config rather than hardcoding.
"""
from __future__ import annotations

from typing import Any

from ..models import Invoice, SAPPostingResult
from ..sap_client import SAPODataClient, SAPPostingError


def build_supplier_invoice_payload(invoice: Invoice, gl_account_fallback: str) -> dict[str, Any]:
    extracted = invoice.extracted
    items: list[dict[str, Any]] = []

    line_items = extracted.line_items or [
        # No line-item detail on the invoice: post a single line for the
        # gross amount so the document still balances.
        None
    ]

    for idx, item in enumerate(line_items, start=1):
        if item is None:
            amount = extracted.net_amount
            tax_code = None
            gl_account = gl_account_fallback
        else:
            amount = item.line_amount
            tax_code = item.tax_code
            gl_account = item.gl_account or gl_account_fallback

        item_payload: dict[str, Any] = {
            "SupplierInvoiceItem": str(idx),
            "SupplierInvoiceItemAmount": str(amount),
            "DocumentCurrency": extracted.currency,
            "TaxCode": tax_code or "",
        }

        if extracted.purchase_order_number:
            # PO-referenced (goods/services already receipted against this
            # PO) - SAP derives the GL account from the PO account
            # assignment, so no GL account is sent here.
            item_payload["PurchaseOrder"] = extracted.purchase_order_number
            item_payload["PurchaseOrderItem"] = f"{idx * 10:05d}"
        else:
            # No PO on the invoice - post directly to a GL account.
            item_payload["GLAccount"] = gl_account

        items.append(item_payload)

    return {
        "CompanyCode": invoice.company_code,
        "DocumentDate": extracted.invoice_date.isoformat(),
        "PostingDate": extracted.invoice_date.isoformat(),
        "SupplierInvoiceIDByInvcgParty": extracted.invoice_number,
        "InvoicingParty": invoice.supplier_id,
        "DocumentCurrency": extracted.currency,
        "InvoiceGrossAmount": str(extracted.gross_amount),
        "DocumentHeaderText": f"Auto-posted from {invoice.source_file}"[:25],
        "to_SupplierInvoiceItem": items,
    }


class SAPPostingAgent:
    def __init__(self, sap_client: SAPODataClient, gl_account_fallback: str) -> None:
        self._sap_client = sap_client
        self._gl_account_fallback = gl_account_fallback

    def post(self, invoice: Invoice) -> SAPPostingResult:
        payload = build_supplier_invoice_payload(invoice, self._gl_account_fallback)
        try:
            created = self._sap_client.create_supplier_invoice(payload)
        except SAPPostingError as exc:
            return SAPPostingResult(success=False, error_message=str(exc))

        return SAPPostingResult(
            success=True,
            sap_document_number=created.get("SupplierInvoice"),
            fiscal_year=created.get("FiscalYear"),
        )
