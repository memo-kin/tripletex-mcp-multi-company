# MCP Server: Tripletex (`src/tripletex_mcp_multi/server.py`)

## Configured Companies

Companies are loaded from `TRIPLETEX_COMPANIES` (env / Secret Manager) at server start. Use the `list_companies` tool to see the names available at runtime. The `company` parameter is **required** on every API tool when more than one company is configured.

## Tools (23)

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
| `download_voucher_pdf` | `/ledger/voucher/{id}/pdf` | voucher_id |
| `search_orders` | `/order` | order_date_from, order_date_to |
| `get_order` | `/order/{id}` (with `orderLines(*)`) | order_id |
| `search_products` | `/product` | — |
| `search_bank_statements` | `/bank/statement` | — |
| `get_balance_sheet` | `/balanceSheet` (saldobalanse; supports `account_number_from`/`account_number_to`, upper bound exclusive) | date_from, date_to (exclusive) |
| `get_income_statement` | `/balanceSheet` filtered to accounts 3000–8999 | date_from, date_to (exclusive) |
| `search_documents` | `/document` | — |
| `get_monthly_status` | `/ledger/monthlyStatus` | — |

All search/get tools accept optional `company`, `fields` (comma-separated), and `max_results` (default 10,000). The `truncated` flag in responses signals when to narrow your query.

`/balanceSheet` is **saldobalanse** (trial balance); it backs both `get_balance_sheet` and `get_income_statement`. Per-row `balanceChange` is period activity in Tripletex's debit-positive convention — revenue (3xxx) is credit-negative.

### PDF tools are transport-aware

`download_invoice_pdf` and `download_voucher_pdf` are the only tools whose return shape depends on transport:

- **stdio (local dev):** write the PDF to disk under `./output/invoices/` or `./output/vouchers/` (cwd-relative), or to `output_path` if provided. Return `saved_path` + `file_size_bytes`.
- **streamable-http (hosted):** return the PDF inline as base64 (`base64_bytes`, `content_type`, `filename`, `size_bytes`) since there is no client-accessible filesystem.

Both call read-only Tripletex GET endpoints. To find voucher ids tied to a supplier+period, use `search_postings` with `supplier_id` + `date_from`/`date_to` and dedupe `voucher.id`.

### Orders

`search_orders` requires `order_date_from`/`order_date_to` (the latter exclusive); `number` is a **substring (contains)** match on the order number. `get_order` returns a single order with its order lines embedded (`fields` defaults to `*,orderLines(*)`) — the `/order/orderline` list endpoint cannot be filtered by parent order, so this is the canonical way to fetch lines.

### Date range convention — `date_to` is exclusive

Every Tripletex tool that takes a `date_to` (or `invoice_date_to` / `order_date_to`) treats the upper bound as **exclusive**, matching `account_number_to`. For an inclusive period query, pass the **first day of the next period**:

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

`TRIPLETEX_COMPANIES` is a JSON array:
```json
[{"name": "company_a", "employee_token": "..."}, {"name": "company_b", "employee_token": "..."}]
```
Each entry can optionally override `consumer_token` and `base_url`. Single-company fallback: set `TRIPLETEX_EMPLOYEE_TOKEN` instead.

## Auth Module (`src/tripletex_mcp_multi/tripletex.py`)

- `TripletexAuthAsync` — async session token management (2-day cache, single force-refresh on 401)
- `CompanyRegistry` — multi-company token registry; `company_required` is true when >1 company configured
- `load_tripletex_companies()` — loads from `TRIPLETEX_COMPANIES`, falls back to `TRIPLETEX_EMPLOYEE_TOKEN`
- `tripletex_get_async()` — authenticated paginated GET helper (returns `total_available`/`returned`/`truncated`/`data`)
- `build_params()` — snake_case→camelCase param builder, drops `None`

## Transports & Layout

- `__main__.py` — `python -m tripletex_mcp_multi` runs **streamable-http** by default (Cloud Run); `--stdio` (or `MCP_TRANSPORT=stdio`) runs stdio for local Claude Code.
- `client.py` — local stdio proxy to a hosted deployment; mints/refreshes Google ID tokens via `gcloud`.
- See `README.md` for local dev, token setup, and Cloud Run deployment.
