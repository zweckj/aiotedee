"""Cloud API client."""

from __future__ import annotations

import logging
from http import HTTPMethod
from typing import Any

from ..const import API_URL_BRIDGE, API_URL_LOCK, API_URL_SYNC
from ..helpers import http_request
from ..models import TedeeBridge
from .base import TedeeClientBase

_LOGGER = logging.getLogger(__name__)


class TedeeCloudClient(TedeeClientBase):
    """Client for the Tedee cloud API.

    Use this for cloud-only access (e.g. listing all bridges, operating locks
    via the cloud).
    """

    def __init__(self, *, personal_token: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._personal_token = personal_token
        self._cloud_headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"PersonalKey {personal_token}",
        }

    # -- Transport implementations ---------------------------------------------

    async def _fetch_locks(self) -> list[dict]:
        r = await http_request(
            API_URL_LOCK,
            HTTPMethod.GET,
            self._cloud_headers,
            self._session,
            self._timeout,
        )
        return r["result"] if isinstance(r, dict) else r

    async def _fetch_sync(self) -> tuple[list[dict], bool]:
        r = await http_request(
            API_URL_SYNC,
            HTTPMethod.GET,
            self._cloud_headers,
            self._session,
            self._timeout,
        )
        result = r["result"] if isinstance(r, dict) else r
        return result, False  # is_local = False

    async def _execute_lock_operation(
        self,
        lock_id: int,
        action: str,
    ) -> None:
        url = f"{API_URL_LOCK}{lock_id}/operation/{action}"
        await http_request(
            url,
            HTTPMethod.POST,
            self._cloud_headers,
            self._session,
            self._timeout,
        )

    # -- Cloud-only methods ----------------------------------------------------

    async def get_bridges(self) -> list[TedeeBridge]:
        """List all bridges from the cloud API."""
        _LOGGER.debug("Getting bridges...")
        r = await http_request(
            API_URL_BRIDGE,
            HTTPMethod.GET,
            self._cloud_headers,
            self._session,
            self._timeout,
        )
        bridges = [TedeeBridge.from_api_response(b) for b in r["result"]]
        _LOGGER.debug("Bridges retrieved successfully")
        return bridges
