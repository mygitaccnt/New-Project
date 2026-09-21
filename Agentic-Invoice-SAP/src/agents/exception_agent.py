"""Routes anything the pipeline can't safely finish to a human-reviewable
exception queue instead of silently dropping it or guessing.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("agentic_invoice_sap.exceptions")


class ExceptionAgent:
    def __init__(self, failed_dir: str) -> None:
        self._failed_dir = Path(failed_dir)
        self._failed_dir.mkdir(parents=True, exist_ok=True)

    def flag(self, source_file: Path, reason: str, details: list[str] | None = None) -> None:
        record = {
            "source_file": str(source_file),
            "reason": reason,
            "details": details or [],
            "flagged_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.warning("Flagging %s for review: %s", source_file.name, reason)

        sidecar = self._failed_dir / f"{source_file.stem}.error.json"
        sidecar.write_text(json.dumps(record, indent=2))

        destination = self._failed_dir / source_file.name
        if source_file.exists():
            source_file.replace(destination)
