"""Tripletex authentication and API helpers (sync + async)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

DEFAULT_MAX_RESULTS = 10_000
PAGE_SIZE = 1000

_CAMEL_RE = re.compile(r"_([a-z])")


def _to_camel(name: str) -> str:
    return _CAMEL_RE.sub(lambda m: m.group(1).upper(), name)


def build_params(**kwargs: Any) -> dict[str, Any]:
    """Build API query params: drop None values, convert snake_case to camelCase."""
    return {_to_camel(k): v for k, v in kwargs.items() if v is not None}


# ---------------------------------------------------------------------------
# Sync auth (used by pipeline)
# ---------------------------------------------------------------------------


class TripletexAuthSync:
    """Sync session token manager for Tripletex."""

    def __init__(
        self,
        client: httpx.Client,
        consumer_token: str,
        employee_token: str,
        base_url: str,
    ) -> None:
        self._client = client
        self._consumer_token = consumer_token
        self._employee_token = employee_token
        self._base_url = base_url
        self._session_token: str | None = None
        self._expiration_date: date | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    def get_token(self) -> str:
        if self._is_expired():
            self._create_session()
        return self._session_token  # type: ignore[return-value]

    def force_refresh(self) -> str:
        self._create_session()
        return self._session_token  # type: ignore[return-value]

    def _is_expired(self) -> bool:
        if self._session_token is None or self._expiration_date is None:
            return True
        today = datetime.now(timezone.utc).date()
        return today >= self._expiration_date

    def _create_session(self) -> None:
        expiration = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        resp = self._client.put(
            f"{self._base_url}/token/session/:create",
            params={
                "consumerToken": self._consumer_token,
                "employeeToken": self._employee_token,
                "expirationDate": expiration,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._session_token = data["value"]["token"]
        self._expiration_date = date.fromisoformat(expiration)


# ---------------------------------------------------------------------------
# Async auth (used by MCP server)
# ---------------------------------------------------------------------------


class TripletexAuthAsync:
    """Async session token manager for Tripletex."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        consumer_token: str,
        employee_token: str,
        base_url: str,
    ) -> None:
        self._client = client
        self._consumer_token = consumer_token
        self._employee_token = employee_token
        self._base_url = base_url
        self._session_token: str | None = None
        self._expiration_date: date | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    async def get_token(self) -> str:
        if self._is_expired():
            await self._create_session()
        return self._session_token  # type: ignore[return-value]

    async def force_refresh(self) -> str:
        await self._create_session()
        return self._session_token  # type: ignore[return-value]

    def _is_expired(self) -> bool:
        if self._session_token is None or self._expiration_date is None:
            return True
        today = datetime.now(timezone.utc).date()
        return today >= self._expiration_date

    async def _create_session(self) -> None:
        expiration = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        resp = await self._client.put(
            f"{self._base_url}/token/session/:create",
            params={
                "consumerToken": self._consumer_token,
                "employeeToken": self._employee_token,
                "expirationDate": expiration,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._session_token = data["value"]["token"]
        self._expiration_date = date.fromisoformat(expiration)


# ---------------------------------------------------------------------------
# Multi-company registry (used by MCP server)
# ---------------------------------------------------------------------------


class CompanyRegistry:
    """Holds per-company TripletexAuthAsync instances."""

    def __init__(self, client: httpx.AsyncClient, companies: list[dict[str, str]]) -> None:
        self._auths: dict[str, TripletexAuthAsync] = {}
        self._names: list[str] = []
        for c in companies:
            name = c["name"].lower()
            self._names.append(c["name"])
            self._auths[name] = TripletexAuthAsync(
                client,
                consumer_token=c["consumer_token"],
                employee_token=c["employee_token"],
                base_url=c["base_url"],
            )

    @property
    def names(self) -> list[str]:
        return list(self._names)

    @property
    def count(self) -> int:
        return len(self._auths)

    @property
    def company_required(self) -> bool:
        return self.count > 1

    def get_auth(self, company: str | None) -> TripletexAuthAsync:
        if self.count == 0:
            raise ValueError("No Tripletex companies configured. Set TRIPLETEX_COMPANIES or TRIPLETEX_EMPLOYEE_TOKEN.")

        if company is None:
            if self.company_required:
                raise ValueError(
                    f"Multiple companies configured — specify 'company' parameter. "
                    f"Available: {', '.join(self._names)}"
                )
            return next(iter(self._auths.values()))

        key = company.lower()
        if key not in self._auths:
            raise ValueError(
                f"Unknown company '{company}'. Available: {', '.join(self._names)}"
            )
        return self._auths[key]


# ---------------------------------------------------------------------------
# Company loader (shared)
# ---------------------------------------------------------------------------


def load_tripletex_companies(consumer_token: str, base_url: str) -> list[dict[str, str]]:
    """Parse TRIPLETEX_COMPANIES JSON or fall back to single TRIPLETEX_EMPLOYEE_TOKEN."""
    raw = os.environ.get("TRIPLETEX_COMPANIES", "").strip()
    if raw:
        entries = json.loads(raw)
        return [
            {
                "name": e["name"],
                "employee_token": e["employee_token"],
                "consumer_token": e.get("consumer_token", consumer_token),
                "base_url": e.get("base_url", base_url),
            }
            for e in entries
        ]

    employee_token = os.environ.get("TRIPLETEX_EMPLOYEE_TOKEN", "")
    if employee_token:
        return [
            {
                "name": "default",
                "employee_token": employee_token,
                "consumer_token": consumer_token,
                "base_url": base_url,
            }
        ]

    return []


# ---------------------------------------------------------------------------
# Sync API helper (used by pipeline)
# ---------------------------------------------------------------------------


def tripletex_get_sync(
    client: httpx.Client,
    auth: TripletexAuthSync,
    path: str,
    params: dict | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[dict]:
    """Paginated GET against Tripletex. Returns the data list."""
    params = dict(params or {})
    token = auth.get_token()
    base_auth = httpx.BasicAuth(username="0", password=token)

    params.setdefault("count", PAGE_SIZE)
    params.setdefault("from", 0)

    all_values: list[dict] = []
    total_available: int | None = None
    retried_auth = False

    while True:
        resp = client.get(f"{auth.base_url}{path}", params=params, auth=base_auth)

        if resp.status_code == 401 and not retried_auth:
            retried_auth = True
            token = auth.force_refresh()
            base_auth = httpx.BasicAuth(username="0", password=token)
            continue

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "2"))
            time.sleep(retry_after)
            continue

        resp.raise_for_status()
        body = resp.json()

        if "value" in body and "values" not in body:
            return [body["value"]]

        values = body.get("values", [])
        total_available = body.get("fullResultSize", len(values))
        all_values.extend(values)

        if len(all_values) >= max_results:
            return all_values[:max_results]
        if len(all_values) >= total_available:
            break

        params["from"] = len(all_values)
        retried_auth = False

    return all_values


# ---------------------------------------------------------------------------
# Async API helper (used by MCP server)
# ---------------------------------------------------------------------------


async def tripletex_get_async(
    client: httpx.AsyncClient,
    auth: TripletexAuthAsync,
    path: str,
    params: dict[str, Any] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, Any]:
    """Generic paginated GET against the Tripletex API.

    Returns {"total_available": int, "returned": int, "truncated": bool, "data": list}.
    """
    params = dict(params or {})

    token = await auth.get_token()
    base_auth = httpx.BasicAuth(username="0", password=token)

    params.setdefault("count", PAGE_SIZE)
    params.setdefault("from", 0)

    all_values: list[dict] = []
    total_available: int | None = None
    retried_auth = False

    while True:
        resp = await client.get(f"{auth.base_url}{path}", params=params, auth=base_auth)

        if resp.status_code == 401 and not retried_auth:
            retried_auth = True
            token = await auth.force_refresh()
            base_auth = httpx.BasicAuth(username="0", password=token)
            continue

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "2"))
            await asyncio.sleep(retry_after)
            continue

        resp.raise_for_status()
        body = resp.json()

        if "value" in body and "values" not in body:
            return {
                "total_available": 1,
                "returned": 1,
                "truncated": False,
                "data": [body["value"]],
            }

        values = body.get("values", [])
        total_available = body.get("fullResultSize", len(values))
        all_values.extend(values)

        if len(all_values) >= max_results:
            all_values = all_values[:max_results]
            break
        if len(all_values) >= total_available:
            break

        params["from"] = len(all_values)
        retried_auth = False

    truncated = len(all_values) < (total_available or 0)
    return {
        "total_available": total_available or len(all_values),
        "returned": len(all_values),
        "truncated": truncated,
        "data": all_values,
    }
