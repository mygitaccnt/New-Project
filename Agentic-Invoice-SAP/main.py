"""CLI entrypoint for the invoice-to-SAP agentic pipeline.

Usage:
    python main.py --once     # process whatever is in the inbox now, then exit
    python main.py --watch    # poll the inbox forever (for a long-running container)
"""
from __future__ import annotations

import argparse
import logging
import time

import anthropic

from src.agents.analyzer_agent import InvoiceAnalyzerAgent
from src.agents.exception_agent import ExceptionAgent
from src.agents.retriever_agent import PDFRetrieverAgent
from src.agents.sap_posting_agent import SAPPostingAgent
from src.agents.validator_agent import InvoiceValidatorAgent
from src.config import Settings
from src.orchestrator import InvoiceProcessingOrchestrator
from src.sap_client import SAPCredentials, SAPODataClient
from src.storage import InvoiceLedger

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("agentic_invoice_sap.main")


def build_orchestrator(settings: Settings) -> InvoiceProcessingOrchestrator:
    anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    sap_client = SAPODataClient(
        SAPCredentials(
            base_url=settings.sap_base_url,
            username=settings.sap_username,
            password=settings.sap_password,
            client=settings.sap_client,
        )
    )
    ledger = InvoiceLedger(settings.ledger_db_path)

    return InvoiceProcessingOrchestrator(
        settings=settings,
        retriever=PDFRetrieverAgent(settings.inbox_dir),
        analyzer=InvoiceAnalyzerAgent(anthropic_client, settings.anthropic_model),
        validator=InvoiceValidatorAgent(ledger),
        sap_poster=SAPPostingAgent(sap_client, gl_account_fallback=settings.sap_gl_account_fallback),
        exception_agent=ExceptionAgent(settings.failed_dir),
        ledger=ledger,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic PDF invoice -> SAP S/4HANA pipeline")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="process the inbox once and exit")
    mode.add_argument("--watch", action="store_true", help="poll the inbox forever")
    args = parser.parse_args()

    settings = Settings.from_env()
    orchestrator = build_orchestrator(settings)

    if args.once:
        count = orchestrator.run_once()
        logger.info("Processed %d file(s)", count)
        return

    logger.info("Watching %s every %ds", settings.inbox_dir, settings.poll_interval_seconds)
    while True:
        count = orchestrator.run_once()
        if count:
            logger.info("Processed %d file(s)", count)
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
