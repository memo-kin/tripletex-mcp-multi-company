# tripletex-mcp-multi-company

A read-only [MCP](https://modelcontextprotocol.io/) server for the **Tripletex** REST API v2 with
**multi-company** support. One server process can authenticate against and serve data from any number
of Tripletex companies; the caller selects which company per tool call via a `company` parameter.

It runs two ways from the same codebase:

- **Local (stdio):** Claude Code (or any MCP client) launches it as a subprocess. Simplest for dev
  against the Tripletex **test tenant**.
- **Hosted (streamable-http):** deploy to a container host such as **Google Cloud Run** and share it
  with a team. A bundled stdio **proxy client** lets each user connect through the hosted server while
  authentication is handled by the platform (e.g. Cloud Run IAM).

23 read-only tools: invoices, postings, vouchers, orders, balance sheet, income statement, PDFs, and
more — see [Tools](#tools).

> **Public repo note:** every deployment example below uses **placeholders**
> (`<YOUR_GCP_PROJECT_ID>`, `<YOUR_CLOUD_RUN_SERVICE_URL>`, etc.). Never commit real project ids,
> service URLs, emails, or tokens. Secrets live in `.env` (gitignored) locally and in your secret
> manager when hosted.

---

## Architecture

```
Claude Code / MCP client
   │
   ├── local:   python -m tripletex_mcp_multi --stdio   ──► Tripletex REST API v2
   │
   └── hosted:  tripletex-mcp-multi-client (stdio proxy)
                   │  HTTPS + Authorization: Bearer <platform id-token>
                   ▼
                Cloud Run service (streamable-http on :8080/mcp)
                   │  python -m tripletex_mcp_multi
                   ▼
                Tripletex REST API v2  (session-token auth)
```

Authentication has two independent layers when hosted: the **platform** authenticates the client→server
hop (e.g. Cloud Run IAM — no app-level auth code), and the **server** authenticates server→Tripletex
using per-company session tokens.

---

## How to get Tripletex tokens

The server needs two kinds of token. Both come from Tripletex, not from this repo.

### 1. Consumer token (one per integration)

Identifies *the integration itself* (the API consumer). It is issued by whoever owns the Tripletex API
integration / partner account and is shared across all companies in a group. Treat it as a secret.
See the [Tripletex API documentation](https://tripletex.no/v2-docs/) and
[API support](https://tripletex.no/api-support/) for issuing one.

Set it as `TRIPLETEX_CONSUMER_TOKEN`.

### 2. Employee / access token (one per company)

Identifies the user the integration acts as **within a specific company**. Generate it in that
company's Tripletex UI:

> **Settings → Our company → API access → Create employee token**
> (requires the accountant/API role on that company)

This is the per-company `employee_token`. For multiple companies, generate one token in each company's
own UI and list them all in `TRIPLETEX_COMPANIES` (see [Configuration](#configuration)). For a single
company, you can instead set `TRIPLETEX_EMPLOYEE_TOKEN`.

Tokens don't auto-expire but can be revoked from the same screen. The server exchanges
`(consumer_token, employee_token)` for short-lived **session tokens** automatically (cached ~2 days,
auto-refreshed on 401) — you never manage session tokens yourself.

### Test vs production tenant

- **Test:** `TRIPLETEX_BASE_URL=https://api-test.tripletex.tech/v2` — the default; safe to experiment.
  Test-tenant tokens are obtained from Tripletex's test environment / API playground, separately from
  prod.
- **Production:** `TRIPLETEX_BASE_URL=https://tripletex.no/v2`.

You can also override `base_url` per company entry in `TRIPLETEX_COMPANIES` to mix test and prod.

---

## Configuration

Copy `.env.example` → `.env` (gitignored) and fill in real values:

| Variable | Purpose |
|----------|---------|
| `TRIPLETEX_BASE_URL` | Tenant base URL (defaults to the **test** tenant). |
| `TRIPLETEX_CONSUMER_TOKEN` | Group/integration-level consumer token. |
| `TRIPLETEX_COMPANIES` | JSON array `[{"name","employee_token", ...}]`. `consumer_token`/`base_url` optional per entry. |
| `TRIPLETEX_EMPLOYEE_TOKEN` | Single-company alternative — set **instead of** `TRIPLETEX_COMPANIES`. |

`name` is a free-form identifier you choose (e.g. `company_a`); use it consistently as the `company`
parameter when calling tools.

---

## Local dev (stdio)

For development against the Tripletex **test tenant**:

```powershell
# 1. Install the package (editable) into a venv at the repo root
python -m venv venv
venv\Scripts\pip install -e .

# 2. Configure credentials (NEVER commit .env)
copy .env.example .env
# edit .env — TRIPLETEX_BASE_URL defaults to api-test.tripletex.tech in the template

# 3. (Optional) Verify it boots — speaks stdio, blocks waiting for MCP messages.
#    A traceback here means env/imports are wrong; clean start = healthy.
venv\Scripts\python.exe -m tripletex_mcp_multi --stdio
```

Register it with Claude Code by copying the committed template and restarting:

```powershell
copy .mcp.json.example .mcp.json
```

`.mcp.json` registers this venv as the `tripletex-dev` server (project-scoped). Restart Claude Code
after editing `src/` — FastMCP doesn't hot-reload.

> `pip` shells (bash/zsh): use `venv/bin/pip` and `source venv/bin/activate`. PowerShell users may
> need `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once to activate the venv.

---

## Hosted deployment (Google Cloud Run)

The repo ships a `Dockerfile` and `cloudbuild.yaml` for a tag-triggered Cloud Run deploy. Set real
values via Cloud Build **trigger substitutions** — they are placeholders in the repo.

### One-time GCP setup

```bash
PROJECT=<YOUR_GCP_PROJECT_ID>
REGION=europe-west1
AR_REPO=<YOUR_ARTIFACT_REGISTRY_REPO>     # e.g. "mcp"
SERVICE=tripletex-mcp-multi

# 1. Enable APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com --project=$PROJECT

# 2. Artifact Registry repo (Docker)
gcloud artifacts repositories create $AR_REPO --repository-format=docker \
  --location=$REGION --project=$PROJECT

# 3. Secrets (values never committed) — consumer token, companies JSON, base URL
printf '%s' '<consumer-token>' | gcloud secrets create tripletex-consumer-token \
  --replication-policy=automatic --data-file=- --project=$PROJECT
gcloud secrets create tripletex-companies --replication-policy=automatic \
  --data-file=companies.json --project=$PROJECT      # [{"name":"company_a","employee_token":"..."}]
printf '%s' 'https://tripletex.no/v2' | gcloud secrets create tripletex-base-url \
  --replication-policy=automatic --data-file=- --project=$PROJECT
```

Grant the **Cloud Build** service account `roles/run.admin`, `roles/iam.serviceAccountUser`,
`roles/artifactregistry.writer`, and `roles/secretmanager.secretAccessor`; grant the **Cloud Run
runtime** service account `roles/secretmanager.secretAccessor` on each secret.

`cloudbuild.yaml` deploys with `--no-traffic`, which Cloud Run rejects on a service's *first* deploy —
bootstrap the first revision once manually with `gcloud run deploy $SERVICE --image=... --set-secrets=...
--set-env-vars=MCP_TRANSPORT=streamable-http --no-allow-unauthenticated`, then create a `^v.*$`
tag-triggered Cloud Build trigger pointed at `cloudbuild.yaml`.

### Release loop

```bash
git push
git tag v0.1.0 && git push origin v0.1.0          # fires Cloud Build
# Cloud Build builds, pushes, deploys --no-traffic with revision tag rev-v0-1-0
pwsh ./scripts/smoke.ps1 -Url https://rev-v0-1-0---$SERVICE-<hash>-ew.a.run.app -Company company_a
gcloud run services update-traffic $SERVICE --to-tags=rev-v0-1-0=100 --region=$REGION --project=$PROJECT
```

Rollback = re-point traffic at a previous `rev-` tag. After the first deploy, set the live `/mcp` URL
as `DEFAULT_SERVICE_URL` in `src/tripletex_mcp_multi/client.py` (or have users set `TRIPLETEX_MCP_URL`).

### Granting access (Cloud Run IAM)

Anyone with `roles/run.invoker` on the service can call it:

```bash
gcloud run services add-iam-policy-binding $SERVICE \
  --member="user:teammate@example.com" --role=roles/run.invoker \
  --region=$REGION --project=$PROJECT
```

### End-user setup (hosted)

After an admin grants `roles/run.invoker`:

```powershell
gcloud auth login
gcloud config set project <YOUR_GCP_PROJECT_ID>

git clone <YOUR_REPO_URL> && cd tripletex-mcp-multi-company
python -m venv venv
venv\Scripts\pip install -e .

# Point the proxy at the hosted service, then register it user-wide:
$env:TRIPLETEX_MCP_URL = "https://<YOUR_CLOUD_RUN_SERVICE_URL>/mcp"
$client = "$PWD\venv\Scripts\tripletex-mcp-multi-client.exe"
claude mcp add --scope user tripletex $client
```

The proxy (`tripletex-mcp-multi-client`) is a tiny stdio MCP server that forwards every request to the
hosted service, minting/refreshing your Google ID token via `gcloud` automatically — end users never
see token-expiry 401s. Restart Claude Code; the Tripletex tools appear in every project.

Two registrations side-by-side is the recommended workflow:

| Scope | Server name | Points at |
|---|---|---|
| Project (`.mcp.json` in this repo) | `tripletex-dev` | local stdio, test tenant |
| User (`claude mcp add ... --scope user`) | `tripletex` | hosted Cloud Run, prod tenant |

---

## Multi-company usage

Every tool that touches company-specific data accepts an optional `company` parameter:

- **Single-company** (`TRIPLETEX_EMPLOYEE_TOKEN`, or one-entry `TRIPLETEX_COMPANIES`): omit `company`.
- **Multi-company:** pass `company="<name>"`. The server raises rather than guessing if you omit it.
- Call `list_companies` to see the configured names.

---

## Tools

23 read-only tools — no writes, no deletes. Full catalogue and parameter docs in
[`agent_docs/mcp_tripletex.md`](agent_docs/mcp_tripletex.md). Highlights:

| Tool | Description |
|------|-------------|
| `list_companies` / `whoami` | Enumerate configured companies / probe auth + identity. |
| `search_postings` / `search_open_postings` | Journal postings by date/account; unmatched open posts. |
| `search_invoices` / `download_invoice_pdf` | Search invoices; fetch invoice PDF. |
| `search_orders` / `get_order` | Search sales orders; fetch one order with its lines. |
| `search_vouchers` / `download_voucher_pdf` | Search vouchers; fetch the voucher/supplier-bill PDF. |
| `get_income_statement` / `get_balance_sheet` | P&L and trial balance for a date range. |
| `search_accounts` / `search_customers` / `search_suppliers` / `search_products` | Master-data lookups. |

### `date_to` is exclusive

Every Tripletex tool that takes `date_to` (or `invoice_date_to` / `order_date_to`) treats the upper
bound as **exclusive**, matching `account_number_to`. For an inclusive period, pass the **first day of
the next period**:

| Period | date_from | date_to |
|--------|-----------|---------|
| January 2026 | `2026-01-01` | `2026-02-01` |
| Q1 2026 | `2026-01-01` | `2026-04-01` |
| Full year 2025 | `2025-01-01` | `2026-01-01` |

This matters most for the income statement: month-end COGS recognition, inventory adjustments, and
accrual vouchers are typically dated to the last day of the month, so `date_to=last-day-of-month`
silently drops them and can flip a profit into a loss.

### PDF tools are transport-aware

`download_invoice_pdf` / `download_voucher_pdf` write to `./output/{invoices,vouchers}/` over **stdio**
and return inline base64 over **streamable-http** (no client-accessible filesystem). Same arguments,
different result schema (`saved_path` vs `base64_bytes`).

---

## Constraints (intentional)

- **Read-only.** No mutation tools — even where Tripletex exposes them.
- **No app-level auth.** When hosted, the platform (Cloud Run IAM) is the only client→server auth layer.
- **Pinned deps.** `pyproject.toml` pins exact versions; bump deliberately.
- **FastMCP 2.x lifespan API.** Access the lifespan dict via `ctx.request_context.lifespan_context[...]`.

---

## License

MIT — see [LICENSE](LICENSE).
