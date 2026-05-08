# tripletex-mcp-multi-company

A standalone, read-only [MCP](https://modelcontextprotocol.io/) server for the **Tripletex** REST API v2 with multi-company support. One server process can serve any number of Tripletex companies; the caller picks which one per tool call.

## What's in this repo

| Component | Location | Description |
|-----------|----------|-------------|
| **Tripletex MCP server** | `mcp/tripletex_server.py` | 19 read-only tools (accounts, postings, invoices, vouchers, balance sheet, income statement, etc.) |
| **Auth + registry** | `auth/tripletex.py` | Sync + async authentication, plus `CompanyRegistry` for multi-company routing |

## Prerequisites

- Python 3.11+ (pinned via `.python-version`)
- A Tripletex consumer token (group-level) and at least one employee token
- [Claude Code](https://claude.ai/code) — or any MCP client — to invoke the tools interactively

## Setup

1. **Create and activate a virtualenv:**

   ```bash
   python -m venv venv
   ```

   | Shell | Activation |
   |-------|------------|
   | PowerShell | `.\venv\Scripts\Activate.ps1` |
   | Git Bash / WSL | `source venv/Scripts/activate` |
   | macOS / Linux | `source venv/bin/activate` |

   PowerShell users may need `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables** — copy `.env.example` to `.env` and fill in real values (see [Credentials](#credentials)):

   ```bash
   cp .env.example .env
   ```

4. **Configure your MCP client** — copy `.mcp.json.example` to `.mcp.json` and replace `<REPO_ROOT>` with the absolute path to this repo:

   ```bash
   cp .mcp.json.example .mcp.json
   ```

5. **Restart Claude Code** so it picks up the new `.mcp.json`.

### Test environment vs production

The default `TRIPLETEX_BASE_URL` is Tripletex's **test environment** (`https://api-test.tripletex.tech/v2`). It's safe to play with and a great way to confirm the server works end-to-end before pointing it at real data. See [Tripletex API support](https://tripletex.no/api-support/) for how to obtain test credentials.

When you're ready to use it against real books, set `TRIPLETEX_BASE_URL=https://tripletex.no/v2` in `.env` (or override per-company in the `TRIPLETEX_COMPANIES` JSON — each entry can carry its own `base_url`).

### Credentials

- `TRIPLETEX_CONSUMER_TOKEN` — your group/organization-level API consumer token, issued by Tripletex.
- `TRIPLETEX_COMPANIES` — JSON array of `{name, employee_token}` per company. Generate each `employee_token` in that company's Tripletex UI: **Settings → Our company → API access → Create employee token** (requires the accountant role on the company). `name` is a free-form identifier you choose; use it consistently as the `company` parameter when calling tools.
- `TRIPLETEX_EMPLOYEE_TOKEN` — single-company alternative; set this **instead of** `TRIPLETEX_COMPANIES` when you only have one company.

Tokens do not auto-expire but can be revoked from the same Tripletex UI screen.

## Multi-company usage

Every tool that touches company-specific data accepts an optional `company` parameter:

- **Single-company** setup (`TRIPLETEX_EMPLOYEE_TOKEN` set, or `TRIPLETEX_COMPANIES` with one entry): omit `company`.
- **Multi-company** setup: pass `company="<company_id>"`. The server raises if you omit it rather than guessing.
- Use the `list_companies` tool to see what's currently configured.

## Tools

All tools are read-only — no writes, no deletes.

| Tool | Description |
|------|-------------|
| `list_companies` | List companies the server is configured for. |
| `whoami` | Probe auth + which company you're hitting. Useful first call. |
| `search_accounts` | Find accounts by number or name. |
| `search_postings` | Search journal postings by date / account. |
| `search_invoices` | Search outgoing invoices. |
| `search_vouchers` | Search vouchers. |
| `get_income_statement` | P&L figures by account for a date range. **Note:** `date_to` is exclusive — use first day of the next period for inclusive month-end ranges. |
| `get_balance_sheet` | Balance sheet figures by account at a given `date`. |
| `download_invoice_pdf` | Download an invoice PDF to disk. Defaults to `./invoices/invoice_{number}_{company}_{date}.pdf`. |

…and more (see `mcp/tripletex_server.py` for the full list and parameter docs).

Example:

```
download_invoice_pdf(invoice_id="123456789", company="company_a")
→ saved_path: invoices/invoice_10066_company_a_2026-04-14.pdf (168 KB)
```

## Running the server standalone

The server speaks stdio. Launch it directly to smoke-test that imports, env vars, and auth all work — without involving an MCP client:

```bash
python mcp/tripletex_server.py
```

It starts and blocks waiting for MCP protocol messages on stdin. A traceback at startup means env vars or imports are wrong; clean exit on Ctrl-C means it's healthy.

## Project structure

```
.
├── .env                        # Credentials (gitignored)
├── .env.example                # Template for .env (tracked)
├── .mcp.json                   # MCP client config (gitignored)
├── .mcp.json.example           # Template for .mcp.json (tracked)
├── .python-version             # Pins Python 3.11 (tracked)
├── LICENSE                     # MIT
├── requirements.txt            # Python dependencies
├── auth/                       # Tripletex auth (sync + async) + company registry
│   ├── __init__.py
│   └── tripletex.py
├── mcp/                        # MCP server (standalone script)
│   └── tripletex_server.py
└── agent_docs/                 # Server reference docs
    └── mcp_tripletex.md
```

## Validation

There is no test suite. After setup, verify with the `whoami` tool — pass any configured `company` value and check the returned identity matches what you expect.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ModuleNotFoundError: No module named 'fastmcp'` (or `httpx`, etc.) | venv not activated, or deps not installed | Re-activate venv (see [Setup](#setup)), `pip install -r requirements.txt` |
| MCP client log: `command not found` for the server | `<REPO_ROOT>` placeholder still in `.mcp.json` | Replace with an absolute path and restart the client |
| `401 Unauthorized` on Tripletex calls | Employee token revoked, or wrong consumer token | Re-issue token in Tripletex UI (Settings → Our company → API access) and update `.env` |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Default Windows PowerShell execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (one-time) |
| Multi-company configured but server complains `company is required` | Tool was called without `company` while multiple are configured | Pass `company="<company_id>"` (use `list_companies` to see options) |
| Income statement totals look wrong for a recent month-end | Tripletex `date_to` is exclusive | Use first day of next period as `date_to` (see [CLAUDE.md](CLAUDE.md#querying-gotchas)) |

## License

MIT — see [LICENSE](LICENSE).
