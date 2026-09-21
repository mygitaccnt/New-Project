"""SQLite-backed ledger: idempotency (don't post the same invoice twice) and
an audit trail of what the pipeline did with every file it touched.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .models import ProcessingStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    supplier_id TEXT,
    invoice_number TEXT,
    status TEXT NOT NULL,
    sap_document_number TEXT,
    error_message TEXT,
    processed_at TEXT NOT NULL,
    UNIQUE (supplier_id, invoice_number)
);
"""


class InvoiceLedger:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def is_duplicate(self, supplier_id: str, invoice_number: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT 1 FROM processed_invoices
                   WHERE supplier_id = ? AND invoice_number = ?
                   AND status = ?""",
                (supplier_id, invoice_number, ProcessingStatus.POSTED.value),
            ).fetchone()
            return row is not None

    def record(
        self,
        source_file: str,
        status: ProcessingStatus,
        supplier_id: Optional[str] = None,
        invoice_number: Optional[str] = None,
        sap_document_number: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO processed_invoices
                       (source_file, supplier_id, invoice_number, status,
                        sap_document_number, error_message, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (supplier_id, invoice_number) DO UPDATE SET
                       source_file=excluded.source_file,
                       status=excluded.status,
                       sap_document_number=excluded.sap_document_number,
                       error_message=excluded.error_message,
                       processed_at=excluded.processed_at""",
                (
                    source_file,
                    supplier_id,
                    invoice_number,
                    status.value,
                    sap_document_number,
                    error_message,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
