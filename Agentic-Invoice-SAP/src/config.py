"""Environment-driven configuration. No secrets are hardcoded anywhere."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    # -- Anthropic --
    anthropic_api_key: str | None
    anthropic_model: str

    # -- SAP S/4HANA OData --
    sap_base_url: str
    sap_username: str
    sap_password: str
    sap_client: str
    sap_default_company_code: str
    sap_gl_account_fallback: str

    # -- Pipeline I/O --
    inbox_dir: str
    processed_dir: str
    failed_dir: str
    ledger_db_path: str
    poll_interval_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"),
            sap_base_url=_require("SAP_BASE_URL").rstrip("/"),
            sap_username=_require("SAP_USERNAME"),
            sap_password=_require("SAP_PASSWORD"),
            sap_client=os.environ.get("SAP_CLIENT", "100"),
            sap_default_company_code=os.environ.get("SAP_DEFAULT_COMPANY_CODE", "1000"),
            sap_gl_account_fallback=_require("SAP_GL_ACCOUNT_FALLBACK"),
            inbox_dir=os.environ.get("PDF_INBOX_DIR", "./data/inbox"),
            processed_dir=os.environ.get("PDF_PROCESSED_DIR", "./data/processed"),
            failed_dir=os.environ.get("PDF_FAILED_DIR", "./data/failed"),
            ledger_db_path=os.environ.get("LEDGER_DB_PATH", "./data/ledger.sqlite3"),
            poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "60")),
        )
