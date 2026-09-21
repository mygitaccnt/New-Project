"""Turns an invoice PDF into structured data using Claude's native PDF support.

This is the one step in the pipeline that genuinely needs a model: invoice
layouts vary per vendor, so a fixed OCR template doesn't generalize. Every
other step (validation, SAP posting) stays deterministic code on purpose -
an LLM has no business making the final call on whether money gets posted.
"""
from __future__ import annotations

import base64
from pathlib import Path

import anthropic

from ..models import ExtractedInvoice

_EXTRACTION_INSTRUCTIONS = """\
You are an accounts-payable data extraction agent. Read the attached invoice
PDF and extract the fields defined by the response schema exactly as they
appear on the document - do not compute, guess, or infer a value that is not
printed on the invoice.

Rules:
- currency must be the ISO 4217 3-letter code (e.g. USD, EUR). Infer it from
  the currency symbol/name on the document if no explicit code is printed.
- net_amount + tax_amount should equal gross_amount; if the document's own
  printed totals don't reconcile, extract the printed values as-is and note
  the discrepancy in extraction_notes rather than adjusting them.
- line_items should reflect every line on the invoice; if the invoice has no
  itemized lines, return an empty list.
- Leave a field null/empty when it is not present on the document - never
  fabricate an invoice number, PO number, or tax id.
"""


class InvoiceAnalyzerAgent:
    def __init__(self, client: anthropic.Anthropic, model: str) -> None:
        self._client = client
        self._model = model

    def analyze(self, pdf_path: Path) -> ExtractedInvoice:
        pdf_data = base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")

        response = self._client.messages.parse(
            model=self._model,
            max_tokens=8000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data,
                            },
                        },
                        {"type": "text", "text": _EXTRACTION_INSTRUCTIONS},
                    ],
                }
            ],
            output_format=ExtractedInvoice,
        )
        return response.parsed_output
