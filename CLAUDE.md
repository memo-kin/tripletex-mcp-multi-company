# CLAUDE.md

## What This Is

A standalone, read-only MCP server for the **Tripletex** REST API v2 with multi-company support. One server process can authenticate against and serve data from any number of Tripletex companies; the caller selects which company per tool call via a `company` parameter.

## How to Run

**MCP server:** Auto-launched via `.mcp.json` (restart Claude Code to reload after code changes).

**Setup:** `python -m venv venv && pip install -r requirements.txt` + `.env` with API credentials.

**Standalone smoke test:** `python mcp/tripletex_server.py` — speaks stdio, blocks waiting for MCP messages. Traceback at startup = misconfigured env/imports.

## Project Structure

```
tripletex-mcp-multi-company/
├── .env / .mcp.json / requirements.txt / LICENSE
├── auth/                    # Sync + async Tripletex auth + multi-company registry
│   ├── __init__.py
│   └── tripletex.py
├── mcp/                     # MCP server (standalone script, no __init__.py)
│   └── tripletex_server.py  # 19 tools, multi-company aware
└── agent_docs/              # Deep reference docs (see below)
    └── mcp_tripletex.md
```

## Architecture

- **`auth/tripletex.py`**: Auth + `CompanyRegistry`. Provides both sync (script) and async (MCP) flavors. `load_tripletex_companies()` reads `TRIPLETEX_COMPANIES` (JSON array) or falls back to a single-company `TRIPLETEX_EMPLOYEE_TOKEN`. Each entry in `TRIPLETEX_COMPANIES` may optionally override `consumer_token` and `base_url`.
- **`mcp/tripletex_server.py`**: Standalone FastMCP server. No `__init__.py` in `mcp/` — that would shadow the pip `mcp` package. The script adds the project root to `sys.path` to import from `auth/`. Default `TRIPLETEX_BASE_URL` is the Tripletex test environment (`https://api-test.tripletex.tech/v2`); set it explicitly to switch to production.

## Multi-company calling convention

Every tool that touches company-specific data accepts an optional `company` parameter:

- If only one company is configured, `company` may be omitted.
- If multiple are configured, `company` is **required** — the server raises rather than silently picking one.
- The value must match a `name` you configured in `TRIPLETEX_COMPANIES`.

## Querying gotchas

**Tripletex `date_to` is exclusive.** Every tool that takes `date_to` (or `invoice_date_to`) drops entries dated on `date_to` itself. For an inclusive period query, pass the **first day of the next period**:

| Period | date_from | date_to |
|--------|-----------|---------|
| January 2026 | `2026-01-01` | `2026-02-01` |
| Q1 2026 | `2026-01-01` | `2026-04-01` |
| Full year 2025 | `2025-01-01` | `2026-01-01` |

This matters most for the income statement: month-end COGS recognition, inventory adjustments, and accrual vouchers are typically dated to the last day of the month, so `date_to=last-day-of-month` silently drops them and can flip a profit into a loss.

## Deep Reference

Before modifying server code, read `agent_docs/mcp_tripletex.md` — it covers the API surface, pagination, rate limits, and tool-by-tool behavior.
