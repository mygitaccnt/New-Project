# Agentic Invoice-to-SAP Pipeline

Retrieves invoice PDFs, uses Claude to extract structured invoice data, and
posts validated invoices into SAP S/4HANA as supplier invoices — with a
human-review exception queue for anything that doesn't check out.

## Why it's built this way

Posting to an ERP is a financial transaction, not a chat response, so only
one step in this pipeline is actually agentic:

```
inbox/*.pdf
   |
   v
[1] PDFRetrieverAgent   -- picks up new files (folder-based; swap in an
   |                        IMAP/SFTP poller if invoices arrive another way)
   v
[2] InvoiceAnalyzerAgent -- the only LLM call: sends the PDF to Claude and
   |                        gets back structured JSON (Pydantic schema)
   v
[3] InvoiceValidatorAgent -- deterministic checks: required fields, amounts
   |                          reconcile, no duplicate invoice number
   v
[4] SAPPostingAgent      -- deterministic mapping to SAP's OData payload,
   |                        posts via API_SUPPLIERINVOICE_PROCESS_SRV
   v
 processed/  (posted)   or   failed/*.error.json  (flagged for a human)
```

Extraction is genuinely hard to hardcode (every vendor formats invoices
differently), so that step uses Claude. Everything downstream — validation,
the SAP field mapping, idempotency — is plain deterministic code, because an
LLM has no business making the final call on whether money gets posted to
a company's books. A SQLite ledger (`storage.py`) makes reprocessing safe:
the same invoice number for the same supplier is never posted twice.

## Setup

```bash
cp .env.example .env      # fill in your Anthropic key and SAP credentials
pip install -r requirements.txt
python main.py --once     # process whatever is in ./data/inbox once
python main.py --watch    # or poll the inbox continuously
```

Drop invoice PDFs into `PDF_INBOX_DIR` (default `./data/inbox`). Each file
ends up in exactly one place:

| Outcome | Where it lands |
|---|---|
| Posted to SAP | `PDF_PROCESSED_DIR` |
| Extraction/validation/posting failed | `PDF_FAILED_DIR`, plus a `<name>.error.json` explaining why |
| Pipeline crashed mid-run | stays in `PDF_INBOX_DIR` — safe to rerun, posting is idempotent |

## Configuration

All configuration is environment-driven (see `.env.example`) — no
credentials are hardcoded anywhere in the code.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Claude API access for the extraction step |
| `SAP_BASE_URL`, `SAP_USERNAME`, `SAP_PASSWORD`, `SAP_CLIENT` | SAP OData connection |
| `SAP_DEFAULT_COMPANY_CODE` | Company code invoices post under |
| `SAP_GL_ACCOUNT_FALLBACK` | GL account used when an invoice has no PO reference and no per-line GL account (must exist in your chart of accounts) |
| `PDF_INBOX_DIR` / `PDF_PROCESSED_DIR` / `PDF_FAILED_DIR` | Pipeline I/O directories |
| `LEDGER_DB_PATH` | SQLite ledger used for idempotency and audit trail |
| `POLL_INTERVAL_SECONDS` | Poll interval for `--watch` mode |

## The SAP integration

Posting uses **API_SUPPLIERINVOICE_PROCESS_SRV**, SAP's standard S/4HANA
OData API for creating supplier invoices (the MIRO-equivalent business
object): https://api.sap.com/api/API_SUPPLIERINVOICE_PROCESS_SRV

`src/sap_client.py` handles the CSRF-token handshake OData writes require
and posts a deep-insert payload (header + line items in one call).
`src/agents/sap_posting_agent.py` builds that payload from the extracted
invoice:

- If the invoice references a purchase order, line items post against that
  PO (`PurchaseOrder`/`PurchaseOrderItem`) and SAP derives the GL account
  from the PO's own account assignment.
- Otherwise, line items post directly to `SAP_GL_ACCOUNT_FALLBACK` (or a
  line's own `gl_account` if Claude found one printed on the invoice).

**This mapping is the one part every real deployment has to customize** —
which GL accounts, cost centers, or PO matching rules apply is specific to
each company's chart of accounts and procurement process. Treat the current
mapping as a working starting point, not a finished one.

## Running tests

```bash
pip install -r requirements.txt pytest
pytest -q
```

Tests cover the Pydantic models, the validator's business rules, and the
SAP payload builder/error handling — all without hitting a real Claude or
SAP endpoint (HTTP calls are mocked).

## Deploying

- `Dockerfile` builds a container that runs `python main.py --watch`.
- `k8s/deployment.yaml` + `k8s/secret.example.yaml` show a single-replica
  Deployment with a PVC for the inbox/ledger data (kept at one replica
  since the SQLite ledger is a single-writer store) and secrets/config
  wired in via `envFrom`. Copy `secret.example.yaml` to `secret.yaml`,
  fill in real credentials, and never commit the filled-in version.
- Wire it into this repo's existing Jenkins/Ansible pipeline the same way
  as the other Dockerized services documented under `Jenkins_Jobs/`.

## Known limitations

- SNAP/EBT-style regulated payment flows and other special AP cases are out
  of scope — this handles standard supplier invoices.
- The extraction prompt asks Claude not to fabricate missing fields, but
  always spot-check the exception queue (`PDF_FAILED_DIR`) rather than
  assuming every posted invoice was extracted perfectly; consider adding a
  human-approval step before posting in a production rollout.
- `SAP_GL_ACCOUNT_FALLBACK` and the PO-matching logic need to be adapted to
  your own SAP configuration before this posts real invoices.
