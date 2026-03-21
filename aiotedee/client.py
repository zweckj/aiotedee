"""The TedeeClient class."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from http import HTTPMethod
from typing import Any, ValuesView

import aiohttp

from .const import (
    API_LOCAL_PORT,
    API_LOCAL_VERSION,
    API_PATH_LOCK,
    API_PATH_PULL,
    API_PATH_UNLOCK,
    API_URL_BRIDGE,
    API_URL_LOCK,
    API_URL_SYNC,
    LOCK_DELAY,
    NUM_RETRIES,
    TIMEOUT,
    UNLOCK_DELAY,
)
from .exceptions import (
    TedeeAuthException,
    TedeeClientException,
    TedeeDataUpdateException,
    TedeeLocalAuthException,
    TedeeRateLimitException,
    TedeeWebhookException,
)
from .helpers import http_request
from .models import TedeeBridge, TedeeLock, TedeeLockState
from .webhook import WEBHOOK_HANDLERS, _noop

_LOGGER = logging.getLogger(__name__)


class TedeeClient:
    """Client for interacting with the Tedee API."""

    def __init__(
        self,
        personal_token: str | None = None,
        local_token: str | None = None,
        local_ip: str | None = None,
        timeout: int = TIMEOUT,
        bridge_id: int | None = None,
        session: aiohttp.ClientSession | None = None,
        api_token_mode_plain: bool = False,
    ) -> None:
        """Initialize the Tedee client.

        Args:
            personal_token: Cloud API personal token.
            local_token: Local bridge API token.
            local_ip: Local bridge IP address.
            timeout: HTTP request timeout in seconds.
            bridge_id: Filter locks to a specific bridge.
            session: Optional shared aiohttp session.
            api_token_mode_plain: Use plain (unsecured) local API token.
        """
        self._personal_token = personal_token
        self._local_token = local_token
        self._local_ip = local_ip
        self._timeout = timeout
        self._bridge_id = bridge_id
        self._api_token_mode_plain = api_token_mode_plain

        self._locks: dict[int, TedeeLock] = {}
        self._use_local_api: bool = bool(local_token and local_ip)
        self._session = session or aiohttp.ClientSession()

        self._cloud_headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"PersonalKey {self._personal_token}",
        }
        self._local_api_base: str = (
            f"http://{local_ip}:{API_LOCAL_PORT}/{API_LOCAL_VERSION}"
        )

        _LOGGER.debug("Using local API: %s", self._use_local_api)

    @classmethod
    async def create(
        cls,
        personal_token: str | None = None,
        local_token: str | None = None,
        local_ip: str | None = None,
        bridge_id: int | None = None,
        timeout: int = TIMEOUT,
    ) -> TedeeClient:
        """Create and initialize a TedeeClient with locks already fetched."""
        client = cls(personal_token, local_token, local_ip, timeout, bridge_id)
        await client.get_locks()
        return client

    # -- Public properties -----------------------------------------------------

    @property
    def locks(self) -> ValuesView[TedeeLock]:
        """Return all locks."""
        return self._locks.values()

    @property
    def locks_dict(self) -> dict[int, TedeeLock]:
        """Return locks keyed by ID."""
        return self._locks

    # -- Lock retrieval & sync -------------------------------------------------

    async def get_locks(self) -> None:
        """Fetch and store all registered locks."""
        result, _ = await self._api_call(
            local_path="/lock",
            cloud_url=API_URL_LOCK,
            http_method=HTTPMethod.GET,
        )
        if result is None:
            raise TedeeClientException("No data returned from get_locks")

        for lock_json in self._filter_by_bridge(result):
            lock = TedeeLock.from_api_response(lock_json)
            self._locks[lock.id] = lock

        if not self._locks:
            raise TedeeClientException("No lock found")

        _LOGGER.debug("Locks retrieved successfully")

    async def sync(self) -> None:
        """Synchronize lock states with the API."""
        _LOGGER.debug("Syncing locks")
        result, is_local = await self._api_call(
            local_path="/lock",
            cloud_url=API_URL_SYNC,
            http_method=HTTPMethod.GET,
        )
        if result is None:
            raise TedeeClientException("No data returned from sync")

        for lock_json in self._filter_by_bridge(result):
            lock_id: int = lock_json["id"]
            lock = self._locks.get(lock_id)
            if lock is None:
                continue
            lock.update_from_api_response(
                lock_json, include_settings=is_local
            )

        _LOGGER.debug("Locks synced successfully")

    # -- Lock operations -------------------------------------------------------

    async def unlock(self, lock_id: int) -> None:
        """Unlock a lock."""
        await self._lock_operation(
            lock_id,
            local_path=f"/lock/{lock_id}/unlock?mode=3",
            cloud_path=f"{API_PATH_UNLOCK}?mode=3",
            name="Unlock",
            delay=UNLOCK_DELAY,
        )

    async def lock(self, lock_id: int) -> None:
        """Lock a lock."""
        await self._lock_operation(
            lock_id,
            local_path=f"/lock/{lock_id}/lock",
            cloud_path=API_PATH_LOCK,
            name="Lock",
            delay=LOCK_DELAY,
        )

    async def open(self, lock_id: int) -> None:
        """Unlock and pull the door latch."""
        delay = self._locks[lock_id].duration_pullspring + 1
        await self._lock_operation(
            lock_id,
            local_path=f"/lock/{lock_id}/unlock?mode=4",
            cloud_path=f"{API_PATH_UNLOCK}?mode=4",
            name="Open",
            delay=delay,
        )

    async def pull(self, lock_id: int) -> None:
        """Pull the door latch only."""
        delay = self._locks[lock_id].duration_pullspring + 1
        await self._lock_operation(
            lock_id,
            local_path=f"/lock/{lock_id}/pull",
            cloud_path=API_PATH_PULL,
            name="Pull",
            delay=delay,
        )

    def is_unlocked(self, lock_id: int) -> bool:
        """Return whether a lock is unlocked."""
        return self._locks[lock_id].state == TedeeLockState.UNLOCKED

    def is_locked(self, lock_id: int) -> bool:
        """Return whether a lock is locked."""
        return self._locks[lock_id].state == TedeeLockState.LOCKED

    # -- Bridge ----------------------------------------------------------------

    async def get_local_bridge(self) -> TedeeBridge:
        """Get bridge information from the local API."""
        if not self._use_local_api:
            raise TedeeClientException("Local API not configured.")
        success, result = await self._local_api_call("/bridge", HTTPMethod.GET)
        if not success or not result:
            raise TedeeClientException("Unable to get local bridge")
        return TedeeBridge.from_api_response(result)

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

    # -- Webhooks --------------------------------------------------------------

    def parse_webhook_message(self, message: dict) -> None:
        """Parse a webhook message sent from the bridge."""
        event = message.get("event")
        data = message.get("data")

        if data is None:
            raise TedeeWebhookException("No data in webhook message.")
        if event == "backend-connection-changed":
            return

        lock_id: int = data.get("deviceId", 0)
        lock = self._locks.get(lock_id)
        if lock is None:
            return

        WEBHOOK_HANDLERS.get(event, _noop)(lock, data)
        self._locks[lock_id] = lock

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
            success, result = await self._local_api_call(
                "/callback", HTTPMethod.GET
            )
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
            await self._local_api_call(
                f"/callback/{webhook_id}", HTTPMethod.DELETE
            )
        except TedeeDataUpdateException as ex:
            _LOGGER.debug("Unable to delete webhook: %s", ex)
        _LOGGER.debug("Webhook deleted successfully.")

    async def cleanup_webhooks_by_host(self, host: str) -> None:
        """Delete all webhooks whose URL contains *host*."""
        _LOGGER.debug("Deleting webhooks for host %s", host)
        try:
            success, result = await self._local_api_call(
                "/callback", HTTPMethod.GET
            )
        except TedeeDataUpdateException as ex:
            _LOGGER.debug("Unable to get webhooks: %s", ex)
            return
        if not success or result is None:
            _LOGGER.debug("Unable to get webhooks")
            return
        for webhook in result:
            if host in webhook["url"]:
                await self.delete_webhook(webhook["id"])

    # -- Internal helpers ------------------------------------------------------

    def _filter_by_bridge(self, locks: list[dict]) -> list[dict]:
        """Filter lock dicts to those belonging to the configured bridge."""
        if not self._bridge_id:
            return locks
        return [
            lock
            for lock in locks
            if lock.get("connectedToId") is None
            or lock.get("connectedToId") == self._bridge_id
        ]

    async def _lock_operation(
        self,
        lock_id: int,
        *,
        local_path: str,
        cloud_path: str,
        name: str,
        delay: float,
    ) -> None:
        """Execute a lock operation (unlock, lock, open, pull)."""
        _LOGGER.debug("%s lock %s...", name, lock_id)
        success, _ = await self._local_api_call(local_path, HTTPMethod.POST)
        if not success:
            url = f"{API_URL_LOCK}{lock_id}{cloud_path}"
            await http_request(
                url,
                HTTPMethod.POST,
                self._cloud_headers,
                self._session,
                self._timeout,
            )
        _LOGGER.debug("%s command successful, id: %s", name, lock_id)
        await asyncio.sleep(delay)

    async def _api_call(
        self,
        *,
        local_path: str,
        cloud_url: str,
        http_method: str,
        json_data: Any = None,
    ) -> tuple[Any, bool]:
        """Make an API call with local-first, cloud-fallback strategy.

        Returns:
            A tuple of (result_data, is_local_call).
        """
        success, result = await self._local_api_call(
            local_path, http_method, json_data
        )
        if success:
            return result, True

        r = await http_request(
            cloud_url,
            http_method,
            self._cloud_headers,
            self._session,
            self._timeout,
            json_data,
        )
        return r["result"] if isinstance(r, dict) else r, False

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
                if not self._personal_token and attempt == NUM_RETRIES:
                    raise TedeeLocalAuthException(
                        "Local API authentication failed."
                    ) from ex
                _LOGGER.debug("Local API authentication failed.")
            except (TedeeClientException, TedeeRateLimitException) as ex:
                if not self._personal_token and attempt == NUM_RETRIES:
                    raise TedeeDataUpdateException(
                        f"Error while calling local API endpoint {path}."
                    ) from ex
                _LOGGER.debug(
                    "Error calling local API %s, retrying with cloud. Error: %s",
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
