"""Tripletex MCP Server — read-only access to Tripletex REST API v2.

Tool surface is identical between stdio and streamable-http transports, with
one exception: the PDF download tools return inline base64 bytes when running
over HTTP (no client-accessible filesystem) and write to ./output/... when
running over stdio (local dev convenience).
"""

from __future__ import annotations

import base64
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastmcp import Context, FastMCP

from .tripletex import (
    CompanyRegistry,
    TripletexAuthAsync,
    build_params,
    load_tripletex_companies,
    tripletex_get_async,
)

load_dotenv()

DEFAULT_MAX_RESULTS = 10_000


def _is_stdio() -> bool:
    return os.environ.get("MCP_TRANSPORT", "streamable-http") == "stdio"


def _resolve(
    ctx: Context, company: str | None
) -> tuple[httpx.AsyncClient, TripletexAuthAsync]:
    lifespan = ctx.request_context.lifespan_context
    return lifespan["client"], lifespan["registry"].get_auth(company)


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Shared httpx client and company registry for the server lifetime."""
    consumer_token = os.environ.get("TRIPLETEX_CONSUMER_TOKEN", "")
    base_url = os.environ.get(
        "TRIPLETEX_BASE_URL", "https://api-test.tripletex.tech/v2"
    )
    companies = load_tripletex_companies(consumer_token, base_url)

    async with httpx.AsyncClient(timeout=30.0) as client:
        registry = CompanyRegistry(client, companies)
        yield {"client": client, "registry": registry}


mcp = FastMCP(
    "Tripletex",
    instructions="Read-only access to Tripletex accounting API v2",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


@mcp.tool()
async def whoami(ctx: Context, company: str | None = None) -> dict:
    """Verify connection and return the current session identity."""
    client, auth = _resolve(ctx, company)
    return await tripletex_get_async(client, auth, "/token/session/>whoAmI")


@mcp.tool()
async def list_companies(ctx: Context) -> dict:
    """List all configured Tripletex companies."""
    registry: CompanyRegistry = ctx.request_context.lifespan_context["registry"]
    return {
        "companies": registry.names,
        "count": registry.count,
        "company_required": registry.company_required,
    }


# ---------------------------------------------------------------------------
# Company & Organization
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_company(
    ctx: Context, fields: str | None = None, company: str | None = None
) -> dict:
    """Get information about the logged-in company."""
    client, auth = _resolve(ctx, company)
    params = build_params(fields=fields)
    return await tripletex_get_async(client, auth, "/company", params)


@mcp.tool()
async def search_departments(
    ctx: Context,
    id: str | None = None,
    name: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search departments. Filter by id or name."""
    client, auth = _resolve(ctx, company)
    params = build_params(id=id, name=name, fields=fields)
    return await tripletex_get_async(client, auth, "/department", params, max_results)


@mcp.tool()
async def search_employees(
    ctx: Context,
    id: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    department_id: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search employees. Filter by name, department, etc."""
    client, auth = _resolve(ctx, company)
    params = build_params(
        id=id,
        first_name=first_name,
        last_name=last_name,
        department_id=department_id,
        fields=fields,
    )
    return await tripletex_get_async(client, auth, "/employee", params, max_results)


# ---------------------------------------------------------------------------
# Customers & Suppliers
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_customers(
    ctx: Context,
    id: str | None = None,
    name: str | None = None,
    email: str | None = None,
    customer_number: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search customers. Filter by name, email, or customer number."""
    client, auth = _resolve(ctx, company)
    params = build_params(
        id=id, name=name, email=email, customer_number=customer_number, fields=fields
    )
    return await tripletex_get_async(client, auth, "/customer", params, max_results)


@mcp.tool()
async def search_suppliers(
    ctx: Context,
    id: str | None = None,
    name: str | None = None,
    email: str | None = None,
    supplier_number: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search suppliers. Filter by name, email, or supplier number."""
    client, auth = _resolve(ctx, company)
    params = build_params(
        id=id, name=name, email=email, supplier_number=supplier_number, fields=fields
    )
    return await tripletex_get_async(client, auth, "/supplier", params, max_results)


# ---------------------------------------------------------------------------
# Ledger & Accounting
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_accounts(
    ctx: Context,
    id: str | None = None,
    number_from: int | None = None,
    number_to: int | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search ledger accounts. Filter by account number range."""
    client, auth = _resolve(ctx, company)
    params = build_params(
        id=id, number_from=number_from, number_to=number_to, fields=fields
    )
    return await tripletex_get_async(
        client, auth, "/ledger/account", params, max_results
    )


@mcp.tool()
async def search_postings(
    ctx: Context,
    date_from: str,
    date_to: str,
    account_id: str | None = None,
    supplier_id: str | None = None,
    customer_id: str | None = None,
    department_id: str | None = None,
    project_id: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search ledger postings. date_from and date_to are required (YYYY-MM-DD).

    date_to is **exclusive** (Tripletex convention) — pass next-day for
    inclusive ranges. E.g. for January 2026: date_to='2026-02-01'.
    """
    client, auth = _resolve(ctx, company)
    params = build_params(
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
        supplier_id=supplier_id,
        customer_id=customer_id,
        department_id=department_id,
        project_id=project_id,
        fields=fields,
    )
    return await tripletex_get_async(
        client, auth, "/ledger/posting", params, max_results
    )


@mcp.tool()
async def search_open_postings(
    ctx: Context,
    date: str,
    account_id: str | None = None,
    customer_id: str | None = None,
    supplier_id: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search open (unmatched) postings as of a date (YYYY-MM-DD)."""
    client, auth = _resolve(ctx, company)
    params = build_params(
        date=date,
        account_id=account_id,
        customer_id=customer_id,
        supplier_id=supplier_id,
        fields=fields,
    )
    return await tripletex_get_async(
        client, auth, "/ledger/posting/openPost", params, max_results
    )


@mcp.tool()
async def search_vouchers(
    ctx: Context,
    date_from: str | None = None,
    date_to: str | None = None,
    id: str | None = None,
    number: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search vouchers. Optionally filter by date range, id, or number.

    date_to is **exclusive** (Tripletex convention) — pass next-day for
    inclusive ranges. E.g. for January 2026: date_to='2026-02-01'.
    """
    client, auth = _resolve(ctx, company)
    params = build_params(
        date_from=date_from,
        date_to=date_to,
        id=id,
        number=number,
        fields=fields,
    )
    return await tripletex_get_async(
        client, auth, "/ledger/voucher", params, max_results
    )


@mcp.tool()
async def search_voucher_types(
    ctx: Context,
    name: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search voucher types. Optionally filter by name."""
    client, auth = _resolve(ctx, company)
    params = build_params(name=name, fields=fields)
    return await tripletex_get_async(
        client, auth, "/ledger/voucherType", params, max_results
    )


# ---------------------------------------------------------------------------
# Invoices & Products
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_invoices(
    ctx: Context,
    invoice_date_from: str | None = None,
    invoice_date_to: str | None = None,
    customer_id: str | None = None,
    is_credit_note: bool | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search invoices. Filter by date range, customer, or credit note status.

    invoice_date_to is **exclusive** (Tripletex convention) — pass next-day for
    inclusive ranges. E.g. for January 2026: invoice_date_to='2026-02-01'.
    """
    client, auth = _resolve(ctx, company)
    params = build_params(
        invoice_date_from=invoice_date_from,
        invoice_date_to=invoice_date_to,
        customer_id=customer_id,
        is_credit_note=is_credit_note,
        fields=fields,
    )
    return await tripletex_get_async(client, auth, "/invoice", params, max_results)


async def _fetch_pdf(
    client: httpx.AsyncClient, auth: TripletexAuthAsync, pdf_path: str
) -> bytes:
    token = await auth.get_token()
    base_auth = httpx.BasicAuth(username="0", password=token)
    url = f"{auth.base_url}{pdf_path}"
    resp = await client.get(url, auth=base_auth)
    if resp.status_code == 401:
        token = await auth.force_refresh()
        base_auth = httpx.BasicAuth(username="0", password=token)
        resp = await client.get(url, auth=base_auth)
    resp.raise_for_status()
    return resp.content


@mcp.tool()
async def download_invoice_pdf(
    ctx: Context,
    invoice_id: str,
    company: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Download an invoice PDF.

    Behavior depends on transport:
    - **streamable-http (default in Cloud Run)**: returns the PDF as
      base64-encoded bytes in the response (`base64_bytes`, `content_type`,
      `filename`, plus invoice metadata). `output_path` is ignored.
    - **stdio (local dev)**: writes to `./output/invoices/invoice_{invoiceNumber}_{company}_{invoiceDate}.pdf`
      relative to the cwd, or to `output_path` if provided. Returns `saved_path`
      and `file_size_bytes`.

    Either way the upstream Tripletex call is read-only (GET /invoice/{id}/pdf).
    """
    client, auth = _resolve(ctx, company)

    meta = await tripletex_get_async(client, auth, f"/invoice/{invoice_id}")
    if not meta["data"]:
        raise ValueError(
            f"Invoice {invoice_id} not found in company {company or 'default'}"
        )
    inv = meta["data"][0]
    invoice_number = inv.get("invoiceNumber")
    invoice_date = inv.get("invoiceDate")
    company_label = company or "default"
    filename = f"invoice_{invoice_number}_{company_label}_{invoice_date}.pdf"

    pdf_bytes = await _fetch_pdf(client, auth, f"/invoice/{invoice_id}/pdf")

    if _is_stdio():
        if output_path is None:
            out_dir = Path.cwd() / "output" / "invoices"
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / filename
        else:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf_bytes)
        return {
            "saved_path": str(target.resolve()),
            "file_size_bytes": len(pdf_bytes),
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "company": company_label,
        }

    return {
        "filename": filename,
        "content_type": "application/pdf",
        "base64_bytes": base64.b64encode(pdf_bytes).decode("ascii"),
        "size_bytes": len(pdf_bytes),
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "company": company_label,
    }


@mcp.tool()
async def download_voucher_pdf(
    ctx: Context,
    voucher_id: str,
    company: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Download a voucher PDF (typically the supplier bill attachment).

    Uses GET /ledger/voucher/{id}/pdf. For posted vouchers backed by an incoming
    supplier bill, this returns that bill's PDF (e.g. shipping invoices from
    Bring/Posten/PostNord). For manually keyed vouchers without an attachment,
    Tripletex returns a generated voucher document.

    Behavior depends on transport:
    - **streamable-http (default in Cloud Run)**: returns base64-encoded bytes
      (`base64_bytes`, `content_type`, `filename`, plus voucher metadata).
    - **stdio (local dev)**: writes to `./output/vouchers/voucher_{number}_{company}_{date}.pdf`
      relative to the cwd, or to `output_path` if provided.

    To find voucher ids tied to a supplier+period, use search_postings with
    supplier_id + date_from/date_to and dedupe the voucher.id field.
    """
    client, auth = _resolve(ctx, company)

    meta = await tripletex_get_async(client, auth, f"/ledger/voucher/{voucher_id}")
    if not meta["data"]:
        raise ValueError(
            f"Voucher {voucher_id} not found in company {company or 'default'}"
        )
    v = meta["data"][0]
    voucher_number = v.get("number")
    voucher_date = v.get("date")
    company_label = company or "default"
    filename = f"voucher_{voucher_number}_{company_label}_{voucher_date}.pdf"

    pdf_bytes = await _fetch_pdf(client, auth, f"/ledger/voucher/{voucher_id}/pdf")

    if _is_stdio():
        if output_path is None:
            out_dir = Path.cwd() / "output" / "vouchers"
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / filename
        else:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf_bytes)
        return {
            "saved_path": str(target.resolve()),
            "file_size_bytes": len(pdf_bytes),
            "voucher_id": voucher_id,
            "voucher_number": voucher_number,
            "voucher_date": voucher_date,
            "company": company_label,
        }

    return {
        "filename": filename,
        "content_type": "application/pdf",
        "base64_bytes": base64.b64encode(pdf_bytes).decode("ascii"),
        "size_bytes": len(pdf_bytes),
        "voucher_id": voucher_id,
        "voucher_number": voucher_number,
        "voucher_date": voucher_date,
        "company": company_label,
    }


@mcp.tool()
async def search_orders(
    ctx: Context,
    order_date_from: str,
    order_date_to: str,
    number: str | None = None,
    customer_id: str | None = None,
    employee_id: str | None = None,
    department_id: str | None = None,
    project_id: str | None = None,
    is_closed: bool | None = None,
    is_show_open_postings: bool | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search sales orders. `order_date_from` and `order_date_to` are required
    by the Tripletex API; all other filters narrow within that window.

    `number` is a **substring (contains) match** on the order number — pass
    "9029" to find order numbers containing 9029.

    `order_date_to` is **exclusive** (Tripletex convention) — pass the next-day
    date for an inclusive end. E.g. for January 2026:
    order_date_from='2026-01-01', order_date_to='2026-02-01'.

    Typical workflow for "find an order by number from a known customer":
    use search_customers to resolve the customer id, then pass it as
    customer_id here alongside number and a wide date range.
    """
    client, auth = _resolve(ctx, company)
    params = build_params(
        order_date_from=order_date_from,
        order_date_to=order_date_to,
        number=number,
        customer_id=customer_id,
        employee_id=employee_id,
        department_id=department_id,
        project_id=project_id,
        is_closed=is_closed,
        is_show_open_postings=is_show_open_postings,
        fields=fields,
    )
    return await tripletex_get_async(client, auth, "/order", params, max_results)


@mcp.tool()
async def get_order(
    ctx: Context,
    order_id: str,
    fields: str | None = None,
    company: str | None = None,
) -> dict:
    """Retrieve a single sales order by id, with its order lines embedded.

    By default returns the full order plus full order line details (product,
    count, unit price, vat, discount, etc.) by requesting
    `fields=*,orderLines(*)`. Override `fields` to customize — e.g. pass
    `fields="id,number,orderDate,customer(name),orderLines(id,description,count,unitPriceExcludingVatCurrency)"`
    to fetch only specific columns.

    Note: Tripletex's `/order/orderline` list endpoint cannot be filtered by
    parent order, so this is the canonical way to get an order's lines.
    """
    client, auth = _resolve(ctx, company)
    params = build_params(fields=fields or "*,orderLines(*)")
    return await tripletex_get_async(client, auth, f"/order/{order_id}", params)


@mcp.tool()
async def search_products(
    ctx: Context,
    id: str | None = None,
    number: str | None = None,
    name: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search products. Filter by id, product number, or name."""
    client, auth = _resolve(ctx, company)
    params = build_params(id=id, number=number, name=name, fields=fields)
    return await tripletex_get_async(client, auth, "/product", params, max_results)


# ---------------------------------------------------------------------------
# Bank & Balance Sheet
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_bank_statements(
    ctx: Context,
    id: str | None = None,
    account_id: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search bank statements. Filter by id or account."""
    client, auth = _resolve(ctx, company)
    params = build_params(id=id, account_id=account_id, fields=fields)
    return await tripletex_get_async(
        client, auth, "/bank/statement", params, max_results
    )


@mcp.tool()
async def get_balance_sheet(
    ctx: Context,
    date_from: str,
    date_to: str,
    account_id: str | None = None,
    account_number_from: int | None = None,
    account_number_to: int | None = None,
    department_id: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Get balance sheet / trial balance (saldobalanse). date_from and date_to required (YYYY-MM-DD).

    Both date_to and account_number_to are **exclusive** (Tripletex convention) —
    pass next-day for inclusive periods. E.g. for January 2026: date_to='2026-02-01'.
    """
    client, auth = _resolve(ctx, company)
    params = build_params(
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
        account_number_from=account_number_from,
        account_number_to=account_number_to,
        department_id=department_id,
        fields=fields,
    )
    return await tripletex_get_async(client, auth, "/balanceSheet", params, max_results)


@mcp.tool()
async def get_income_statement(
    ctx: Context,
    date_from: str,
    date_to: str,
    department_id: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Get income statement (resultat) for date range (YYYY-MM-DD).

    Wraps /balanceSheet (saldobalanse) filtered to accounts 3000-8999 — Norwegian
    chart-of-accounts P&L range. Each row's `balanceChange` is the period's
    activity; revenue accounts (3xxx) are credit-negative per Tripletex convention.

    date_to is **exclusive** (Tripletex convention) — pass next-day for
    inclusive periods. E.g. for January 2026: date_to='2026-02-01'.
    Critical: month-end COGS/accrual vouchers are typically dated to the last
    day of the month, so an off-by-one here can drop material P&L entries.
    """
    client, auth = _resolve(ctx, company)
    params = build_params(
        date_from=date_from,
        date_to=date_to,
        account_number_from=3000,
        account_number_to=9000,
        department_id=department_id,
        fields=fields,
    )
    return await tripletex_get_async(client, auth, "/balanceSheet", params, max_results)


# ---------------------------------------------------------------------------
# Documents & Monthly Status
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_documents(
    ctx: Context,
    id: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Search documents. Optionally filter by id."""
    client, auth = _resolve(ctx, company)
    params = build_params(id=id, fields=fields)
    return await tripletex_get_async(client, auth, "/document", params, max_results)


@mcp.tool()
async def get_monthly_status(
    ctx: Context,
    date_from: str | None = None,
    date_to: str | None = None,
    fields: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    company: str | None = None,
) -> dict:
    """Get monthly accounting status (lock status, VAT returns, etc.).

    date_to is **exclusive** (Tripletex convention) — pass next-day for
    inclusive ranges. E.g. for January 2026: date_to='2026-02-01'.
    """
    client, auth = _resolve(ctx, company)
    params = build_params(date_from=date_from, date_to=date_to, fields=fields)
    return await tripletex_get_async(
        client, auth, "/ledger/monthlyStatus", params, max_results
    )
