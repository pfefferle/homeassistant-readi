"""Client for the re@di CKAN portal."""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from .const import PACKAGE_URL, SEARCH_URL

TIMEOUT = aiohttp.ClientTimeout(total=30)


class ReadiError(Exception):
    """The portal could not be reached or answered with an error."""


class ReadiClient:
    """Small wrapper around the CKAN action API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, url: str, params: dict[str, Any]) -> Any:
        try:
            async with self._session.get(url, params=params, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ReadiError(str(err)) from err
        if not isinstance(body, dict) or not body.get("success"):
            raise ReadiError(f"Portal error for {url}")
        return body["result"]

    async def package(self, name: str) -> dict[str, Any]:
        """Return the metadata of a dataset."""
        return await self._get(PACKAGE_URL, {"id": name})

    async def records(
        self,
        resource_id: str,
        limit: int,
        filters: dict[str, str] | None = None,
        fields: list[str] | None = None,
        sort: str | None = "timestamp desc",
    ) -> list[dict[str, Any]]:
        """Return records of a resource, newest first by default."""
        params: dict[str, Any] = {"resource_id": resource_id, "limit": limit}
        if sort:
            params["sort"] = sort
        if filters:
            params["filters"] = json.dumps(filters, ensure_ascii=False)
        if fields:
            params["fields"] = ",".join(fields)
        result = await self._get(SEARCH_URL, params)
        return result.get("records", [])
