"""Watches the inbox directory for new invoice PDFs.

A folder drop is the lowest-common-denominator source: point an SFTP sync,
an email-to-folder rule, or a scanner's output directory at PDF_INBOX_DIR
and this agent picks up whatever lands there. Swap `iter_new_pdfs` for an
IMAP/Graph-API/SFTP poller if invoices arrive some other way; nothing else
in the pipeline depends on how the PDF got onto disk.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator


class PDFRetrieverAgent:
    def __init__(self, inbox_dir: str) -> None:
        self._inbox_dir = Path(inbox_dir)
        self._inbox_dir.mkdir(parents=True, exist_ok=True)

    def iter_new_pdfs(self) -> Iterator[Path]:
        for path in sorted(self._inbox_dir.glob("*.pdf")):
            if path.is_file():
                yield path
