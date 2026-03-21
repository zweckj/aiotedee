"""Client classes for interacting with the Tedee API.

Class hierarchy::

    TedeeClientBase          - shared state, properties, business logic
    ├── TedeeLocalClient     - local bridge API transport + webhook management
    ├── TedeeCloudClient     - cloud API transport + get_bridges()
    └── TedeeClient          - combined local-first / cloud-fallback (backward compat)
         (TedeeLocalClient, TedeeCloudClient)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from abc import abstractmethod
from http import HTTPMethod
from typing import Any, ValuesView

from aiohttp import ClientSession

from .const import (
    API_LOCAL_PORT,
    API_LOCAL_VERSION,
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
from .webhook import WEBHOOK_HANDLERS

_LOGGER = logging.getLogger(__name__)


# =============================================================================
# Base client
# =============================================================================


class TedeeClientBase:
    """Base class with shared state management and business logic.

    Subclasses must implement the three transport methods:
    :meth:`_fetch_locks`, :meth:`_fetch_sync`, and
    :meth:`_execute_lock_operation`.
    """

    def __init__(
        self,
        *,
        timeout: int = TIMEOUT,
        bridge_id: int | None = None,
        session: ClientSession | None = None,
        **_kwargs: Any,
    ) -> None:
        self._timeout = timeout
        self._bridge_id = bridge_id
        self._locks: dict[int, TedeeLock] = {}
        self._session = session or ClientSession()
        # Default: no cloud credentials (overridden by TedeeCloudClient).
        self._personal_token: str | None = None

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
        result = await self._fetch_locks()
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
        result, is_local = await self._fetch_sync()
        if result is None:
            raise TedeeClientException("No data returned from sync")

        for lock_json in self._filter_by_bridge(result):
            lock_id: int = lock_json["id"]
            lock = self._locks.get(lock_id)
            if lock is None:
                continue
            lock.update_from_api_response(lock_json, include_settings=is_local)

        _LOGGER.debug("Locks synced successfully")

    # -- Lock operations -------------------------------------------------------

    async def unlock(self, lock_id: int) -> None:
        """Unlock a lock."""
        _LOGGER.debug("Unlock lock %s...", lock_id)
        await self._execute_lock_operation(lock_id, "unlock?mode=3")
        _LOGGER.debug("Unlock command successful, id: %s", lock_id)
        await asyncio.sleep(UNLOCK_DELAY)

    async def lock(self, lock_id: int) -> None:
        """Lock a lock."""
        _LOGGER.debug("Lock lock %s...", lock_id)
        await self._execute_lock_operation(lock_id, "lock")
        _LOGGER.debug("Lock command successful, id: %s", lock_id)
        await asyncio.sleep(LOCK_DELAY)

    async def open(self, lock_id: int) -> None:
        """Unlock and pull the door latch."""
        delay = self._locks[lock_id].duration_pullspring + 1
        _LOGGER.debug("Open lock %s...", lock_id)
        await self._execute_lock_operation(lock_id, "unlock?mode=4")
        _LOGGER.debug("Open command successful, id: %s", lock_id)
        await asyncio.sleep(delay)

    async def pull(self, lock_id: int) -> None:
        """Pull the door latch only."""
        delay = self._locks[lock_id].duration_pullspring + 1
        _LOGGER.debug("Pull lock %s...", lock_id)
        await self._execute_lock_operation(lock_id, "pull")
        _LOGGER.debug("Pull command successful, id: %s", lock_id)
        await asyncio.sleep(delay)

    def is_unlocked(self, lock_id: int) -> bool:
        """Return whether a lock is unlocked."""
        return self._locks[lock_id].state == TedeeLockState.UNLOCKED

    def is_locked(self, lock_id: int) -> bool:
        """Return whether a lock is locked."""
        return self._locks[lock_id].state == TedeeLockState.LOCKED

    # -- Webhooks (parsing only; management methods live in TedeeLocalClient) --

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

        handler = WEBHOOK_HANDLERS.get(event)
        if handler is None:
            _LOGGER.debug("Unknown webhook event: %s", event)
            return
        handler(lock, data)
        self._locks[lock_id] = lock

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

    # -- Abstract transport methods (subclasses must implement) ----------------

    @abstractmethod
    async def _fetch_locks(self) -> list[dict]:
        """Fetch raw lock data from the API."""

    @abstractmethod
    async def _fetch_sync(self) -> tuple[list[dict], bool]:
        """Fetch sync data. Returns ``(data, is_local)``."""

    @abstractmethod
    async def _execute_lock_operation(
        self,
        lock_id: int,
        action: str,
    ) -> None:
        """Execute a single lock command (unlock/lock/open/pull)."""


# =============================================================================
# Local client
# =============================================================================


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


# =============================================================================
# Cloud client
# =============================================================================


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


# =============================================================================
# Combined client (backward-compatible)
# =============================================================================


class TedeeClient(TedeeLocalClient, TedeeCloudClient):
    """Combined client: local-first with cloud-fallback.

    This is the main entry point for most users.  When both a *local_token*
    (+ *local_ip*) and a *personal_token* are provided, API calls first
    attempt the local bridge and transparently fall back to the Tedee cloud.
    """

    def __init__(
        self,
        personal_token: str | None = None,
        local_token: str | None = None,
        local_ip: str | None = None,
        timeout: int = TIMEOUT,
        bridge_id: int | None = None,
        session: ClientSession | None = None,
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
        super().__init__(
            personal_token=personal_token or "",
            local_token=local_token or "",
            local_ip=local_ip or "",
            api_token_mode_plain=api_token_mode_plain,
            timeout=timeout,
            bridge_id=bridge_id,
            session=session,
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

    # -- Transport implementations (local-first, cloud-fallback) ---------------

    async def _fetch_locks(self) -> list[dict]:
        if self._use_local_api:
            success, result = await self._local_api_call("/lock", HTTPMethod.GET)
            if success and result is not None:
                return result

        r = await http_request(
            API_URL_LOCK,
            HTTPMethod.GET,
            self._cloud_headers,
            self._session,
            self._timeout,
        )
        return r["result"] if isinstance(r, dict) else r

    async def _fetch_sync(self) -> tuple[list[dict], bool]:
        if self._use_local_api:
            success, result = await self._local_api_call("/lock", HTTPMethod.GET)
            if success and result is not None:
                return result, True

        r = await http_request(
            API_URL_SYNC,
            HTTPMethod.GET,
            self._cloud_headers,
            self._session,
            self._timeout,
        )
        result = r["result"] if isinstance(r, dict) else r
        return result, False

    async def _execute_lock_operation(
        self,
        lock_id: int,
        action: str,
    ) -> None:
        if self._use_local_api:
            path = f"/lock/{lock_id}/{action}"
            success, _ = await self._local_api_call(path, HTTPMethod.POST)
            if success:
                return

        url = f"{API_URL_LOCK}{lock_id}/operation/{action}"
        await http_request(
            url,
            HTTPMethod.POST,
            self._cloud_headers,
            self._session,
            self._timeout,
        )
