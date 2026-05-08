# MCP Server: Tripletex (`mcp/tripletex_server.py`)

## Configured Companies

Companies are loaded from `TRIPLETEX_COMPANIES` in `.env` at server start. Use the `list_companies` tool to see the names available at runtime. The `company` parameter is **required** on every API tool when more than one company is configured.

## Tools (20)

| Tool | Endpoint | Required Params |
|------|----------|----------------|
| `list_companies` | — (local) | — |
| `whoami` | `/token/session/>whoAmI` | — |
| `get_company` | `/company` | — |
| `search_departments` | `/department` | — |
| `search_employees` | `/employee` | — |
| `search_customers` | `/customer` | — |
| `search_suppliers` | `/supplier` | — |
| `search_accounts` | `/ledger/account` | — |
| `search_postings` | `/ledger/posting` | date_from, date_to |
| `search_open_postings` | `/ledger/posting/openPost` | date |
| `search_vouchers` | `/ledger/voucher` | — |
| `search_voucher_types` | `/ledger/voucherType` | — |
| `search_invoices` | `/invoice` | — |
| `download_invoice_pdf` | `/invoice/{id}/pdf` | invoice_id |
| `search_products` | `/product` | — |
| `search_bank_statements` | `/bank/statement` | — |
| `get_balance_sheet` | `/balanceSheet` (saldobalanse; supports `account_number_from`/`account_number_to`, upper bound exclusive) | date_from, date_to (exclusive) |
| `get_income_statement` | `/balanceSheet` filtered to accounts 3000–8999 | date_from, date_to (exclusive) |
| `search_documents` | `/document` | — |
| `get_monthly_status` | `/ledger/monthlyStatus` | — |

All search/get tools accept optional `company`, `fields` (comma-separated), and `max_results` (default 10,000). The `truncated` flag in responses signals when to narrow your query. `download_invoice_pdf` is the only tool that writes a binary file to disk (default `./invoices/`); all others return JSON.

`/balanceSheet` is **saldobalanse** (trial balance); it backs both `get_balance_sheet` and `get_income_statement`. Per-row `balanceChange` is period activity in Tripletex's debit-positive convention — revenue (3xxx) is credit-negative.

### Date range convention — `date_to` is exclusive

Every Tripletex tool that takes a `date_to` (or `invoice_date_to`) treats the upper bound as **exclusive**, matching `account_number_to`. For an inclusive period query, pass the **first day of the next period**:

| Period | date_from | date_to |
|--------|-----------|---------|
| January 2026 | `2026-01-01` | `2026-02-01` |
| Q1 2026 | `2026-01-01` | `2026-04-01` |
| Full year 2025 | `2025-01-01` | `2026-01-01` |

This matters for the P&L: month-end COGS recognition, inventory adjustments, and accrual vouchers are typically dated to the last day of the month. Using `date_to=last-day-of-month` silently drops these and can flip a profit into a loss.

## API Reference

- **Production:** `https://tripletex.no/v2`
- **Test environment:** `https://api-test.tripletex.tech/v2`
- **API docs:** `https://tripletex.no/v2-docs/`
- **Auth:** Basic auth with username `0` and session token as password
- **Pagination:** offset-based (`from` + `count`), page size 1000, max 10,000 results

## Multi-Company Config

`TRIPLETEX_COMPANIES` is a JSON array in `.env`:
```json
[{"name": "company_a", "employee_token": "eyJ..."}, {"name": "company_b", "employee_token": "eyJ..."}]
```
Each entry can optionally override `consumer_token` and `base_url`. Single-company fallback: set `TRIPLETEX_EMPLOYEE_TOKEN` instead.

## Auth Module (`auth/tripletex.py`)

- `TripletexAuthSync` (pipeline) / `TripletexAuthAsync` (MCP) — session token management
- `CompanyRegistry` — multi-company token registry
- `load_tripletex_companies()` — loads from `TRIPLETEX_COMPANIES` env var
- `tripletex_get_sync()` / `tripletex_get_async()` — authenticated GET helpers
- `build_params()` — pagination parameter builder
