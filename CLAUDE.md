# CLAUDE.md

## What This Is

A read-only MCP server for the **Tripletex** REST API v2 with multi-company support. One process can
authenticate against and serve data from any number of Tripletex companies; the caller selects which
company per tool call via a `company` parameter. Packaged so it runs **locally over stdio** or
**hosted over streamable-http** (e.g. Google Cloud Run) from the same code.

> **Public, MIT-licensed repo.** Never commit proprietary values — GCP project ids, live service
> URLs, real emails, or any token. Deployment files use `<PLACEHOLDER>` substitutions; secrets live
> in `.env` (gitignored) or a secret manager.

## Hard invariants — do not violate

- **Read-only.** Never add Tripletex mutation tools (POST/PUT/DELETE). Wrap GET only.
- **No app-level auth.** When hosted, the platform (Cloud Run IAM) is the only client→server auth.
  Don't add bearer/API-key middleware or token validation in the app.
- **No proprietary values in the repo.** Keep `cloudbuild.yaml`/`client.py`/`smoke.ps1`/`README`
  placeholders generic; real values go on the Cloud Build trigger or in env.
- **Pinned deps.** Exact versions in `pyproject.toml`. Bumps are deliberate.
- **FastMCP 2.x.** Use `ctx.request_context.lifespan_context[...]`; the older `ctx.lifespan_context`
  raises `AttributeError` at runtime.
- **PDF tools stay transport-aware.** stdio writes to `./output/`; http returns inline base64. Keep
  the split — don't unify the return shape.

## How to Run

- **Local stdio (dev):** `pip install -e .`, copy `.env.example`→`.env` (test tenant), then
  `python -m tripletex_mcp_multi --stdio`. `.mcp.json` (copied from `.mcp.json.example`) auto-registers
  the `tripletex-dev` server. Restart Claude Code after `src/` edits — FastMCP doesn't hot-reload.
- **Hosted http:** `python -m tripletex_mcp_multi` defaults to streamable-http on `:$PORT/mcp`. Built
  by `Dockerfile`, deployed by `cloudbuild.yaml` on `v*` tags. End users connect through the
  `tripletex-mcp-multi-client` stdio proxy. See `README.md` for the full release loop.

## Project Structure

```
tripletex-mcp-multi-company/
├── pyproject.toml / Dockerfile / cloudbuild.yaml / .dockerignore
├── .env.example / .mcp.json.example / .python-version / LICENSE
├── scripts/smoke.ps1            # post-deploy verification (init + tools/list + whoami)
├── src/tripletex_mcp_multi/
│   ├── __main__.py              # transport switch (stdio vs streamable-http; env MCP_TRANSPORT)
│   ├── server.py                # FastMCP instance + 23 @mcp.tool() definitions
│   ├── tripletex.py             # TripletexAuthAsync, CompanyRegistry, tripletex_get_async (paginator)
│   └── client.py                # end-user stdio proxy → hosted HTTPS; gcloud-token refresh
└── agent_docs/mcp_tripletex.md  # deep reference (API surface, pagination, tool-by-tool behavior)
```

Console scripts (from `pyproject.toml`): `tripletex-mcp-multi` (server) and
`tripletex-mcp-multi-client` (proxy). Auth is **async-only** (no sync flavor).

## Multi-company calling convention

- One company configured → `company` may be omitted.
- Multiple configured → `company` is **required**; the server raises rather than guessing.
- The value must match a `name` from `TRIPLETEX_COMPANIES`. `list_companies` enumerates them.

## Querying gotchas

**Tripletex `date_to` is exclusive.** Every tool that takes `date_to` (or `invoice_date_to` /
`order_date_to`) drops entries dated on `date_to` itself. For an inclusive period, pass the **first day
of the next period**:

| Period | date_from | date_to |
|--------|-----------|---------|
| January 2026 | `2026-01-01` | `2026-02-01` |
| Q1 2026 | `2026-01-01` | `2026-04-01` |
| Full year 2025 | `2025-01-01` | `2026-01-01` |

This matters most for the income statement: month-end COGS recognition, inventory adjustments, and
accrual vouchers are typically dated to the last day of the month, so `date_to=last-day-of-month`
silently drops them and can flip a profit into a loss.

## Deep Reference

Before modifying server code, read `agent_docs/mcp_tripletex.md` — API surface, pagination, rate
limits, transport-aware PDFs, and tool-by-tool behavior.
