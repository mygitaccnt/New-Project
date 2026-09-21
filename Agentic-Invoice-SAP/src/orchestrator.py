"""Wires the agents into a per-file pipeline:

    retrieve -> analyze (Claude) -> validate -> post to SAP -> record

Every file ends in exactly one of three places: `processed/` (posted to
SAP), `failed/` (flagged for human review, with a .error.json explaining
why), or still in `inbox/` (a crash mid-run - safe to reprocess, since the
ledger's duplicate check makes posting idempotent).
"""
from __future__ import annotations

import logging
from pathlib import Path

from .agents.analyzer_agent import InvoiceAnalyzerAgent
from .agents.exception_agent import ExceptionAgent
from .agents.retriever_agent import PDFRetrieverAgent
from .agents.sap_posting_agent import SAPPostingAgent
from .agents.validator_agent import InvoiceValidatorAgent
from .config import Settings
from .models import Invoice, ProcessingStatus
from .storage import InvoiceLedger

logger = logging.getLogger("agentic_invoice_sap.orchestrator")


class InvoiceProcessingOrchestrator:
    def __init__(
        self,
        settings: Settings,
        retriever: PDFRetrieverAgent,
        analyzer: InvoiceAnalyzerAgent,
        validator: InvoiceValidatorAgent,
        sap_poster: SAPPostingAgent,
        exception_agent: ExceptionAgent,
        ledger: InvoiceLedger,
    ) -> None:
        self._settings = settings
        self._retriever = retriever
        self._analyzer = analyzer
        self._validator = validator
        self._sap_poster = sap_poster
        self._exception_agent = exception_agent
        self._ledger = ledger

    def run_once(self) -> int:
        """Process every PDF currently in the inbox. Returns the count processed."""
        processed = 0
        for pdf_path in self._retriever.iter_new_pdfs():
            self._process_file(pdf_path)
            processed += 1
        return processed

    def _process_file(self, pdf_path: Path) -> None:
        logger.info("Processing %s", pdf_path.name)

        try:
            extracted = self._analyzer.analyze(pdf_path)
        except Exception as exc:  # noqa: BLE001 - any extraction failure is a review case
            self._exception_agent.flag(pdf_path, f"extraction failed: {exc}")
            self._ledger.record(str(pdf_path), ProcessingStatus.VALIDATION_FAILED, error_message=str(exc))
            return

        supplier_id = extracted.vendor_tax_id or extracted.vendor_name
        invoice = Invoice(
            source_file=str(pdf_path),
            company_code=self._settings.sap_default_company_code,
            supplier_id=supplier_id,
            extracted=extracted,
        )

        validation = self._validator.validate(extracted, supplier_id)
        if not validation.is_valid:
            self._exception_agent.flag(pdf_path, "validation failed", validation.errors)
            self._ledger.record(
                str(pdf_path),
                ProcessingStatus.VALIDATION_FAILED,
                supplier_id=supplier_id,
                invoice_number=extracted.invoice_number,
                error_message="; ".join(validation.errors),
            )
            return

        result = self._sap_poster.post(invoice)
        if not result.success:
            self._exception_agent.flag(pdf_path, f"SAP posting failed: {result.error_message}")
            self._ledger.record(
                str(pdf_path),
                ProcessingStatus.POSTING_FAILED,
                supplier_id=supplier_id,
                invoice_number=extracted.invoice_number,
                error_message=result.error_message,
            )
            return

        self._ledger.record(
            str(pdf_path),
            ProcessingStatus.POSTED,
            supplier_id=supplier_id,
            invoice_number=extracted.invoice_number,
            sap_document_number=result.sap_document_number,
        )

        processed_dir = Path(self._settings.processed_dir)
        processed_dir.mkdir(parents=True, exist_ok=True)
        pdf_path.replace(processed_dir / pdf_path.name)
        logger.info(
            "Posted %s as SAP supplier invoice %s (fiscal year %s)",
            pdf_path.name,
            result.sap_document_number,
            result.fiscal_year,
        )
