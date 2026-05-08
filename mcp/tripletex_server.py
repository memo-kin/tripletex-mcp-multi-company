"""Tripletex MCP Server — read-only access to Tripletex REST API v2."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to sys.path so we can import auth/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from contextlib import asynccontextmanager

import httpx
from fastmcp import Context, FastMCP

from auth.tripletex import (
    CompanyRegistry,
    TripletexAuthAsync,
    build_params,
    load_tripletex_companies,
    tripletex_get_async,
)

DEFAULT_MAX_RESULTS = 10_000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve(ctx: Context, company: str | None) -> tuple[httpx.AsyncClient, TripletexAuthAsync]:
    """Extract client and resolve company auth from context."""
    client: httpx.AsyncClient = ctx.lifespan_context["client"]
    registry: CompanyRegistry = ctx.lifespan_context["registry"]
    return client, registry.get_auth(company)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Shared httpx client and company registry for the server lifetime."""
    consumer_token = os.environ.get("TRIPLETEX_CONSUMER_TOKEN", "")
    base_url = os.environ.get("TRIPLETEX_BASE_URL", "https://api-test.tripletex.tech/v2")
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
# Tools — Utility
# ---------------------------------------------------------------------------


@mcp.tool()
async def whoami(ctx: Context, company: str | None = None) -> dict:
    """Verify connection and return the current session identity."""
    client, auth = _resolve(ctx, company)
    return await tripletex_get_async(client, auth, "/token/session/>whoAmI")


@mcp.tool()
async def list_companies(ctx: Context) -> dict:
    """List all configured Tripletex companies."""
    registry: CompanyRegistry = ctx.lifespan_context["registry"]
    return {
        "companies": registry.names,
        "count": registry.count,
        "company_required": registry.company_required,
    }


# ---------------------------------------------------------------------------
# Tools — Company & Organization
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_company(ctx: Context, fields: str | None = None, company: str | None = None) -> dict:
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
# Tools — Customers & Suppliers
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
# Tools — Ledger & Accounting
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
    return await tripletex_get_async(client, auth, "/ledger/account", params, max_results)


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
    return await tripletex_get_async(client, auth, "/ledger/posting", params, max_results)


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
    return await tripletex_get_async(client, auth, "/ledger/voucher", params, max_results)


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
# Tools — Invoices & Products
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


@mcp.tool()
async def download_invoice_pdf(
    ctx: Context,
    invoice_id: str,
    company: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Download an invoice PDF and save it to disk.

    Unlike the other Tripletex tools, this writes a binary file. If `output_path`
    is omitted, saves to ./invoices/invoice_{invoiceNumber}_{company}_{invoiceDate}.pdf
    relative to the project root. Overwrites silently if the file already exists.

    Returns saved_path, file_size_bytes, and the invoice metadata used to build
    the filename.
    """
    client, auth = _resolve(ctx, company)

    invoice_number: int | None = None
    invoice_date: str | None = None

    if output_path is None:
        meta = await tripletex_get_async(client, auth, f"/invoice/{invoice_id}")
        if not meta["data"]:
            raise ValueError(
                f"Invoice {invoice_id} not found in company {company or 'default'}"
            )
        inv = meta["data"][0]
        invoice_number = inv.get("invoiceNumber")
        invoice_date = inv.get("invoiceDate")
        project_root = Path(__file__).resolve().parent.parent
        out_dir = project_root / "invoices"
        out_dir.mkdir(parents=True, exist_ok=True)
        company_label = company or "default"
        target = out_dir / f"invoice_{invoice_number}_{company_label}_{invoice_date}.pdf"
    else:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

    token = await auth.get_token()
    base_auth = httpx.BasicAuth(username="0", password=token)
    pdf_url = f"{auth.base_url}/invoice/{invoice_id}/pdf"

    resp = await client.get(pdf_url, auth=base_auth)
    if resp.status_code == 401:
        token = await auth.force_refresh()
        base_auth = httpx.BasicAuth(username="0", password=token)
        resp = await client.get(pdf_url, auth=base_auth)
    resp.raise_for_status()

    target.write_bytes(resp.content)

    return {
        "saved_path": str(target.resolve()),
        "file_size_bytes": len(resp.content),
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "company": company or "default",
    }


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
# Tools — Bank & Balance Sheet
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
    return await tripletex_get_async(client, auth, "/bank/statement", params, max_results)


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
# Tools — Documents & Monthly Status
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
