"""Local bridge API client."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from http import HTTPMethod
from typing import Any

from ..const import API_LOCAL_PORT, API_LOCAL_VERSION, NUM_RETRIES
from ..exceptions import (
    TedeeAuthException,
    TedeeClientException,
    TedeeDataUpdateException,
    TedeeLocalAuthException,
    TedeeRateLimitException,
    TedeeWebhookException,
)
from ..helpers import http_request
from ..models import TedeeBridge
from .base import TedeeClientBase

_LOGGER = logging.getLogger(__name__)


class TedeeLocalClient(TedeeClientBase):
    """Client for the local Tedee bridge API.

    Use this when communicating directly with a Tedee bridge on the local
    network.  Provides webhook management and local bridge queries in addition
    to the standard lock operations.
    """

    def __init__(
        self,
        *,
        local_token: str,
        local_ip: str,
        api_token_mode_plain: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._local_token = local_token
        self._local_ip = local_ip
        self._api_token_mode_plain = api_token_mode_plain
        self._use_local_api: bool = bool(local_token and local_ip)
        self._local_api_base: str = (
            f"http://{local_ip}:{API_LOCAL_PORT}/{API_LOCAL_VERSION}"
        )

    # -- Transport implementations ---------------------------------------------

    async def _fetch_locks(self) -> list[dict]:
        success, result = await self._local_api_call("/lock", HTTPMethod.GET)
        if not success or result is None:
            raise TedeeClientException("No data returned from local API")
        return result

    async def _fetch_sync(self) -> tuple[list[dict], bool]:
        success, result = await self._local_api_call("/lock", HTTPMethod.GET)
        if not success or result is None:
            raise TedeeClientException("No data returned from local API")
        return result, True  # is_local = True

    async def _execute_lock_operation(
        self,
        lock_id: int,
        action: str,
    ) -> None:
        path = f"/lock/{lock_id}/{action}"
        success, _ = await self._local_api_call(path, HTTPMethod.POST)
        if not success:
            raise TedeeClientException(
                f"Local lock operation failed for lock {lock_id}"
            )

    # -- Local-only: bridge ----------------------------------------------------

    async def get_local_bridge(self) -> TedeeBridge:
        """Get bridge information from the local API."""
        if not self._use_local_api:
            raise TedeeClientException("Local API not configured.")
        success, result = await self._local_api_call("/bridge", HTTPMethod.GET)
        if not success or not result:
            raise TedeeClientException("Unable to get local bridge")
        return TedeeBridge.from_api_response(result)

    # -- Local-only: webhook management ----------------------------------------

    async def update_webhooks(
        self, webhook_url: str, headers_bridge_sends: list | None = None
    ) -> None:
        """Overwrite all webhooks with a single one."""
        _LOGGER.debug("Updating webhooks to %s", webhook_url)
        data = [{"url": webhook_url, "headers": headers_bridge_sends or []}]
        await self._local_api_call("/callback", HTTPMethod.PUT, data)
        _LOGGER.debug("Webhooks updated successfully.")

    async def register_webhook(
        self, webhook_url: str, headers_bridge_sends: list | None = None
    ) -> int:
        """Register a webhook and return the webhook ID."""
        _LOGGER.debug("Registering webhook %s", webhook_url)
        data = {"url": webhook_url, "headers": headers_bridge_sends or []}
        try:
            success, result = await self._local_api_call(
                "/callback", HTTPMethod.POST, data
            )
        except TedeeDataUpdateException as ex:
            raise TedeeWebhookException("Unable to register webhook") from ex
        if not success:
            raise TedeeWebhookException("Unable to register webhook")
        _LOGGER.debug("Webhook registered successfully.")

        if isinstance(result, dict) and "id" in result:
            return result["id"]

        for webhook in await self.get_webhooks():
            if webhook["url"] == webhook_url:
                return webhook["id"]
        raise TedeeWebhookException("Webhook id not found")

    async def get_webhooks(self) -> list[dict[str, Any]]:
        """Get all registered webhooks."""
        _LOGGER.debug("Getting webhooks...")
        try:
            success, result = await self._local_api_call("/callback", HTTPMethod.GET)
        except TedeeDataUpdateException as ex:
            raise TedeeWebhookException("Unable to get webhooks") from ex
        if not success or result is None:
            raise TedeeWebhookException("Unable to get webhooks")
        _LOGGER.debug("Webhooks retrieved successfully.")
        return result

    async def delete_webhooks(self) -> None:
        """Delete all webhooks."""
        _LOGGER.debug("Deleting webhooks...")
        try:
            await self._local_api_call("/callback", HTTPMethod.PUT, [])
        except TedeeDataUpdateException as ex:
            _LOGGER.debug("Unable to delete webhooks: %s", ex)
        _LOGGER.debug("Webhooks deleted successfully.")

    async def delete_webhook(self, webhook_id: int) -> None:
        """Delete a specific webhook."""
        _LOGGER.debug("Deleting webhook %s", webhook_id)
        try:
            await self._local_api_call(f"/callback/{webhook_id}", HTTPMethod.DELETE)
        except TedeeDataUpdateException as ex:
            _LOGGER.debug("Unable to delete webhook: %s", ex)
        _LOGGER.debug("Webhook deleted successfully.")

    async def cleanup_webhooks_by_host(self, host: str) -> None:
        """Delete all webhooks whose URL contains *host*."""
        _LOGGER.debug("Deleting webhooks for host %s", host)
        try:
            success, result = await self._local_api_call("/callback", HTTPMethod.GET)
        except TedeeDataUpdateException as ex:
            _LOGGER.debug("Unable to get webhooks: %s", ex)
            return
        if not success or result is None:
            _LOGGER.debug("Unable to get webhooks")
            return
        for webhook in result:
            if host in webhook["url"]:
                await self.delete_webhook(webhook["id"])

    # -- Local API infrastructure ----------------------------------------------

    async def _local_api_call(
        self, path: str, http_method: str, json_data: Any = None
    ) -> tuple[bool, Any | None]:
        """Call the local bridge API with retries.

        Returns:
            A tuple of (success, response_data).
        """
        if not self._use_local_api:
            return False, None

        for attempt in range(1, NUM_RETRIES + 1):
            try:
                _LOGGER.debug("Local API call: %s %s", http_method, path)
                result = await http_request(
                    self._local_api_base + path,
                    http_method,
                    self._local_api_header,
                    self._session,
                    self._timeout,
                    json_data,
                )
            except TedeeAuthException as ex:
                if attempt == NUM_RETRIES:
                    raise TedeeLocalAuthException(
                        "Local API authentication failed."
                    ) from ex
                _LOGGER.debug("Local API authentication failed.")
            except (TedeeClientException, TedeeRateLimitException) as ex:
                if attempt == NUM_RETRIES:
                    raise TedeeDataUpdateException(
                        f"Error while calling local API endpoint {path}."
                    ) from ex
                _LOGGER.debug(
                    "Error calling local API %s, retrying. Error: %s",
                    path,
                    type(ex).__name__,
                    exc_info=True,
                )
            else:
                return True, result
            await asyncio.sleep(0.5)

        return False, None

    @property
    def _local_api_header(self) -> dict[str, str]:
        """Build the local API authentication header."""
        if not self._local_token:
            return {}
        if self._api_token_mode_plain:
            token = self._local_token
        else:
            ms = time.time_ns() // 1_000_000
            raw = f"{self._local_token}{ms}"
            token = hashlib.sha256(raw.encode()).hexdigest() + str(ms)
        return {"Content-Type": "application/json", "api_token": token}
