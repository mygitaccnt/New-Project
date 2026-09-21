"""Thin client for the SAP S/4HANA Supplier Invoice OData API.

Uses API_SUPPLIERINVOICE_PROCESS_SRV (the standard S/4HANA API for creating
supplier invoices, the MIRO-equivalent OData service) via a deep insert:
one POST carrying the invoice header plus its line items.

Reference: https://api.sap.com/api/API_SUPPLIERINVOICE_PROCESS_SRV
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import requests


class SAPPostingError(Exception):
    """Raised when SAP rejects a supplier invoice (business or technical error)."""


@dataclass
class SAPCredentials:
    base_url: str
    username: str
    password: str
    client: str


class SAPODataClient:
    """Handles the CSRF-token handshake OData write operations require and
    posts a deep-insert supplier invoice payload.
    """

    SERVICE_PATH = "/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV"
    ENTITY_SET = "A_SupplierInvoice"

    def __init__(self, credentials: SAPCredentials, session: requests.Session | None = None) -> None:
        self._creds = credentials
        self._session = session or requests.Session()
        self._session.auth = (credentials.username, credentials.password)
        self._session.headers.update({"sap-client": credentials.client})

    def _service_url(self, suffix: str = "") -> str:
        return f"{self._creds.base_url}{self.SERVICE_PATH}{suffix}"

    def _fetch_csrf_token(self) -> str:
        response = self._session.get(
            self._service_url("/"),
            headers={"X-CSRF-Token": "Fetch", "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        token = response.headers.get("X-CSRF-Token")
        if not token:
            raise SAPPostingError("SAP did not return an X-CSRF-Token; check the service is CSRF-protected and reachable")
        return token

    def create_supplier_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a deep-insert supplier invoice document.

        `payload` must already be shaped as SAP expects, see
        `agents.sap_posting_agent.build_supplier_invoice_payload`.
        Returns the parsed JSON body of the created A_SupplierInvoice entity.
        Raises SAPPostingError with SAP's own error message on any failure.
        """
        csrf_token = self._fetch_csrf_token()
        response = self._session.post(
            self._service_url(f"/{self.ENTITY_SET}"),
            json=payload,
            headers={
                "X-CSRF-Token": csrf_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Idempotency: a retried POST with the same key must not create
                # a second invoice document in SAP.
                "SAP-REQUEST-ID": uuid.uuid4().hex,
            },
            timeout=60,
        )
        if response.status_code not in (200, 201):
            raise SAPPostingError(self._extract_error_message(response))
        return response.json().get("d", response.json())

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            body = response.json()
            message = body.get("error", {}).get("message", {})
            if isinstance(message, dict):
                return message.get("value", response.text)
            return str(message) or response.text
        except ValueError:
            return f"HTTP {response.status_code}: {response.text[:500]}"
