"""Local stdio MCP proxy → hosted Tripletex MCP server.

Claude Code launches this as a stdio child process. It transparently forwards
every JSON-RPC request to the hosted streamable-HTTP server on Cloud Run,
minting and refreshing Google ID tokens via `gcloud auth print-identity-token`
so end users never have to think about ~1h token expiry.

Configure the upstream once it is deployed by setting the TRIPLETEX_MCP_URL
environment variable to your service's `/mcp` endpoint (the DEFAULT_SERVICE_URL
below is a placeholder — replace it or override via env).

Refresh strategy:
- proactive: when cached token is older than TOKEN_MAX_AGE_SECONDS (50 min,
  ~10 min before the actual 60 min expiry)
- reactive: on a 401 from the upstream, force a refresh and retry the request
  exactly once
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Generator

import httpx
from fastmcp import FastMCP
from fastmcp.client.transports import StreamableHttpTransport

# Replace with your deployed Cloud Run URL (ending in /mcp), or set TRIPLETEX_MCP_URL.
DEFAULT_SERVICE_URL = "https://<YOUR_CLOUD_RUN_SERVICE_URL>/mcp"
TOKEN_MAX_AGE_SECONDS = 50 * 60


def _gcloud_path() -> str:
    """Find a working gcloud executable, preferring the .cmd shim on Windows."""
    for name in ("gcloud.cmd", "gcloud"):
        path = shutil.which(name)
        if path:
            return path
    print(
        "ERROR: gcloud not found on PATH. Install the Google Cloud SDK from "
        "https://cloud.google.com/sdk/docs/install",
        file=sys.stderr,
    )
    sys.exit(1)


def _mint_id_token(gcloud: str) -> str:
    """Mint a Google ID token. Exits the process with a friendly error on failure."""
    try:
        result = subprocess.run(
            [gcloud, "auth", "print-identity-token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except subprocess.CalledProcessError as exc:
        print(
            "ERROR: `gcloud auth print-identity-token` failed. Run `gcloud auth login` "
            f"and try again.\nstderr: {exc.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("ERROR: gcloud timed out minting an ID token.", file=sys.stderr)
        sys.exit(1)

    token = result.stdout.strip()
    if not token:
        print("ERROR: gcloud returned an empty ID token.", file=sys.stderr)
        sys.exit(1)
    return token


class GCPIdentityAuth(httpx.Auth):
    """httpx.Auth that injects a refreshing Google ID token bearer."""

    def __init__(self, gcloud_path: str) -> None:
        self._gcloud = gcloud_path
        self._token: str | None = None
        self._minted_at: float = 0.0

    def _refresh(self) -> None:
        self._token = _mint_id_token(self._gcloud)
        self._minted_at = time.monotonic()

    def _stale(self) -> bool:
        return (
            self._token is None
            or (time.monotonic() - self._minted_at) > TOKEN_MAX_AGE_SECONDS
        )

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        if self._stale():
            self._refresh()
        request.headers["Authorization"] = f"Bearer {self._token}"
        response = yield request

        if response.status_code == 401:
            # Token may have been revoked / clock skewed / IAM flapped — try once more.
            self._refresh()
            request.headers["Authorization"] = f"Bearer {self._token}"
            yield request


def main() -> None:
    url = os.environ.get("TRIPLETEX_MCP_URL", DEFAULT_SERVICE_URL)
    gcloud = _gcloud_path()

    auth = GCPIdentityAuth(gcloud)
    # Fail fast at startup if auth is broken, rather than after Claude Code
    # has already spawned us and is waiting for tools/list.
    auth._refresh()

    transport = StreamableHttpTransport(url, auth=auth)
    proxy = FastMCP.as_proxy(transport)
    proxy.run()  # default transport: stdio


if __name__ == "__main__":
    main()
