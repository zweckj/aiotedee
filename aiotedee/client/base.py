"""Base client class with shared state management and business logic."""

from __future__ import annotations

import asyncio
import logging
from abc import abstractmethod
from typing import Any, ValuesView

from aiohttp import ClientSession

from ..const import LOCK_DELAY, TIMEOUT, UNLOCK_DELAY
from ..exceptions import TedeeClientException, TedeeWebhookException
from ..models import TedeeLock, TedeeLockState
from ..webhook import WEBHOOK_HANDLERS

_LOGGER = logging.getLogger(__name__)


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
