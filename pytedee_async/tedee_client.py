"""The TedeeClient class."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from http import HTTPMethod
from typing import Any, ValuesView

import aiohttp

from .bridge import TedeeBridge
from .const import (
    API_LOCAL_PORT,
    API_LOCAL_VERSION,
    API_PATH_LOCK,
    API_PATH_PULL,
    API_PATH_UNLOCK,
    API_URL_BRIDGE,
    API_URL_LOCK,
    API_URL_SYNC,
    LOCAL_CALL_MIN_DISTANCE,
    LOCK_DELAY,
    TIMEOUT,
    UNLOCK_DELAY,
)
from .exception import (
    TedeeAuthException,
    TedeeClientException,
    TedeeDataUpdateException,
    TedeeLocalAuthException,
    TedeeRateLimitException,
    TedeeWebhookException,
)
from .helpers import http_request
from .lock import TedeeLock, TedeeLockState

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
    ):
        """Constructor"""
        self._available = False
        self._personal_token = personal_token
        self._locks_dict: dict[int, TedeeLock] = {}
        self._local_token = local_token
        self._local_ip = local_ip
        self._timeout = timeout
        self._bridge_id = bridge_id

        self._use_local_api: bool = bool(local_token and local_ip)
        self._last_local_call: float | None = None

        if session is None:
            self._session = aiohttp.ClientSession()
        else:
            self._session = session

        _LOGGER.debug("Using local API: %s", str(self._use_local_api))

        # Create the api header with new token"
        self._api_header: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": "PersonalKey " + str(self._personal_token),
        }
        self._local_api_path: str = (
            f"http://{local_ip}:{API_LOCAL_PORT}/{API_LOCAL_VERSION}"
        )

    @classmethod
    async def create(
        cls,
        personal_token: str | None = None,
        local_token: str | None = None,
        local_ip: str | None = None,
        bridge_id: int | None = None,
        timeout=TIMEOUT,
    ) -> TedeeClient:
        """Create a new instance of the TedeeClient, which is initialized."""
        self = cls(personal_token, local_token, local_ip, timeout, bridge_id)
        await self.get_locks()
        return self

    @property
    def locks(self) -> ValuesView:
        """Return a list of locks"""
        return self._locks_dict.values()

    @property
    def locks_dict(self) -> dict[int, TedeeLock]:
        """Return all locks."""
        return self._locks_dict

    async def get_locks(self) -> None:
        """Get the list of registered locks"""
        local_call_success, result = await self._local_api_call("/lock", HTTPMethod.GET)
        if not local_call_success:
            r = await http_request(
                API_URL_LOCK,
                HTTPMethod.GET,
                self._api_header,
                self._session,
                self._timeout,
            )
            result = r["result"]
        _LOGGER.debug("Locks %s", result)

        if result is None:
            raise TedeeClientException('No data returned in "result" from get_locks')

        for lock_json in result:
            if self._bridge_id:
                # if bridge id is set, only get locks for that bridge
                connected_to_id: int | None = lock_json.get("connectedToId")
                if connected_to_id is not None and connected_to_id != self._bridge_id:
                    continue

            lock_id = lock_json["id"]
            lock_name = lock_json["name"]
            lock_type = lock_json["type"]

            (
                is_connected,
                state,
                battery_level,
                is_charging,
                state_change_result,
            ) = self.parse_lock_properties(lock_json)
            (
                is_enabled_pullspring,
                duration_pullspring,
            ) = self.parse_pull_spring_settings(lock_json)

            lock = TedeeLock(
                lock_name,
                lock_id,
                lock_type,
                state,
                battery_level,
                is_connected,
                is_charging,
                state_change_result,
                is_enabled_pullspring,
                duration_pullspring,
            )

            self._locks_dict[lock_id] = lock

        if lock_id is None:
            raise TedeeClientException("No lock found")

        _LOGGER.debug("Locks retrieved successfully...")

    async def sync(self) -> None:
        """Sync locks"""
        _LOGGER.debug("Syncing locks")
        local_call_success, result = await self._local_api_call("/lock", HTTPMethod.GET)
        if not local_call_success:
            r = await http_request(
                API_URL_SYNC,
                HTTPMethod.GET,
                self._api_header,
                self._session,
                self._timeout,
            )
            result = r["result"]

        if result is None:
            raise TedeeClientException('No data returned in "result" from sync')

        for lock_json in result:
            if self._bridge_id:
                # if bridge id is set, only get locks for that bridge
                connected_to_id: int | None = lock_json.get("connectedToId")
                if connected_to_id is not None and connected_to_id != self._bridge_id:
                    continue

            lock_id = lock_json["id"]

            lock = self.locks_dict[lock_id]

            (
                lock.is_connected,
                lock.state,
                lock.battery_level,
                lock.is_charging,
                lock.state_change_result,
            ) = self.parse_lock_properties(lock_json)

            if local_call_success:
                (
                    lock.is_enabled_pullspring,
                    lock.duration_pullspring,
                ) = self.parse_pull_spring_settings(lock_json)

            self._locks_dict[lock_id] = lock
        _LOGGER.debug("Locks synced successfully")

    async def get_local_bridge(self) -> TedeeBridge:
        """Get the local bridge"""
        if not self._use_local_api:
            raise TedeeClientException("Local API not configured.")
        local_call_success, result = await self._local_api_call(
            "/bridge", HTTPMethod.GET
        )
        if not local_call_success or not result:
            raise TedeeClientException("Unable to get local bridge")
        bridge_serial = result["serialNumber"]
        bridge_name = result["name"]
        return TedeeBridge(0, bridge_serial, bridge_name)

    async def get_bridges(self) -> list[TedeeBridge]:
        """List all bridges."""
        _LOGGER.debug("Getting bridges...")
        r = await http_request(
            API_URL_BRIDGE,
            HTTPMethod.GET,
            self._api_header,
            self._session,
            self._timeout,
        )
        result = r["result"]
        bridges = []
        for bridge_json in result:
            bridge_id = bridge_json["id"]
            bridge_serial = bridge_json["serialNumber"]
            bridge_name = bridge_json["name"]
            bridge = TedeeBridge(
                bridge_id,
                bridge_serial,
                bridge_name,
            )
            bridges.append(bridge)
        _LOGGER.debug("Bridges retrieved successfully...")
        return bridges

    async def unlock(self, lock_id: int) -> None:
        """Unlock method"""
        _LOGGER.debug("Unlocking lock %s...", str(lock_id))
        local_call_success, _ = await self._local_api_call(
            f"/lock/{lock_id}/unlock?mode=3", HTTPMethod.POST
        )
        if not local_call_success:
            url = API_URL_LOCK + str(lock_id) + API_PATH_UNLOCK + "?mode=3"
            await http_request(
                url,
                HTTPMethod.POST,
                self._api_header,
                self._session,
                self._timeout,
            )
        _LOGGER.debug("unlock command successful, id: %d ", lock_id)
        await asyncio.sleep(UNLOCK_DELAY)

    async def lock(self, lock_id: int) -> None:
        """'Lock method"""
        _LOGGER.debug("Locking lock %s...", str(lock_id))
        local_call_success, _ = await self._local_api_call(
            f"/lock/{lock_id}/lock", HTTPMethod.POST
        )
        if not local_call_success:
            url = API_URL_LOCK + str(lock_id) + API_PATH_LOCK
            await http_request(
                url,
                HTTPMethod.POST,
                self._api_header,
                self._session,
                self._timeout,
            )
        _LOGGER.debug("lock command successful, id: %s", lock_id)
        await asyncio.sleep(LOCK_DELAY)

    # pulling
    async def open(self, lock_id: int) -> None:
        """Unlock the door and pull the door latch"""
        _LOGGER.debug("Opening lock %s...", str(lock_id))
        local_call_success, _ = await self._local_api_call(
            f"/lock/{lock_id}/unlock?mode=4", HTTPMethod.POST
        )
        if not local_call_success:
            url = API_URL_LOCK + str(lock_id) + API_PATH_UNLOCK + "?mode=4"
            await http_request(
                url,
                HTTPMethod.POST,
                self._api_header,
                self._session,
                self._timeout,
            )
        _LOGGER.debug("Open command successful, id: %s", lock_id)
        await asyncio.sleep(self._locks_dict[lock_id].duration_pullspring + 1)

    async def pull(self, lock_id: int) -> None:
        """Only pull the door latch"""
        _LOGGER.debug("Pulling latch for lock %s...", str(lock_id))
        local_call_success, _ = await self._local_api_call(
            f"/lock/{lock_id}/pull", HTTPMethod.POST
        )
        if not local_call_success:
            url = API_URL_LOCK + str(lock_id) + API_PATH_PULL
            await http_request(
                url,
                HTTPMethod.POST,
                self._api_header,
                self._session,
                self._timeout,
            )
        _LOGGER.debug("Open command not successful, id: %s", lock_id)
        await asyncio.sleep(self._locks_dict[lock_id].duration_pullspring + 1)

    def is_unlocked(self, lock_id: int) -> bool:
        """Return is a specific lock is unlocked"""
        lock = self._locks_dict[lock_id]
        return lock.state == TedeeLockState.UNLOCKED

    def is_locked(self, lock_id: int) -> bool:
        """Return is a specific lock is locked"""
        lock = self._locks_dict[lock_id]
        return lock.state == TedeeLockState.LOCKED

    def parse_lock_properties(self, json_properties: dict):
        """Parse the lock properties"""
        connected = bool(json_properties.get("isConnected", False))

        lock_properties = json_properties.get("lockProperties")

        if lock_properties is not None:
            state = lock_properties.get("state", 9)
            battery_level = lock_properties.get("batteryLevel", 50)
            is_charging = lock_properties.get("isCharging", False)
            state_change_result = lock_properties.get("stateChangeResult", 0)
        else:
            # local call does not have lock properties
            state = json_properties.get("state", 9)
            battery_level = json_properties.get("batteryLevel", 50)
            is_charging = bool(json_properties.get("isCharging", False))
            state_change_result = json_properties.get("jammed", 0)

        return connected, state, battery_level, is_charging, state_change_result

    def parse_pull_spring_settings(self, settings: dict):
        """Parse the pull spring settings"""
        device_settings = settings.get("deviceSettings", {})
        pull_spring_enabled = bool(device_settings.get("pullSpringEnabled", False))
        pull_spring_duration = device_settings.get("pullSpringDuration", 5)
        return pull_spring_enabled, pull_spring_duration

    def _calculate_secure_local_token(self) -> str:
        """Calculate the secure token"""
        if not self._local_token:
            return ""
        ms = time.time_ns() // 1_000_000
        secure_token = self._local_token + str(ms)
        secure_token = hashlib.sha256(secure_token.encode("utf-8")).hexdigest()
        secure_token += str(ms)
        return secure_token

    def _get_local_api_header(self, secure: bool = True) -> dict[str, str]:
        """Get the local api header"""
        if not self._local_token:
            return {}
        token = self._calculate_secure_local_token() if secure else self._local_token
        return {"Content-Type": "application/json", "api_token": token}

    async def _local_api_call(
        self, path: str, http_method: str, json_data=None
    ) -> tuple[bool, Any | None]:
        """Call the local api"""
        if self._use_local_api:
            if (
                self._last_local_call
                and time.time() - self._last_local_call < LOCAL_CALL_MIN_DISTANCE
            ):
                await asyncio.sleep(LOCAL_CALL_MIN_DISTANCE)
            try:
                _LOGGER.debug("Getting locks from Local API...")
                self._last_local_call = time.time()
                r = await http_request(
                    self._local_api_path + path,
                    http_method,
                    self._get_local_api_header(),
                    self._session,
                    self._timeout,
                    json_data,
                )
                return True, r
            except TedeeAuthException as ex:
                msg = "Local API authentication failed."
                if not self._personal_token:
                    raise TedeeLocalAuthException(msg) from ex

                _LOGGER.debug(msg)
            except (TedeeClientException, TedeeRateLimitException) as ex:
                if not self._personal_token:
                    _LOGGER.debug(
                        "Error while calling local API endpoint %s. Error: %s. Full error: %s",
                        path,
                        {type(ex).__name__},
                        str(ex),
                        exc_info=True,
                    )
                    raise TedeeDataUpdateException(
                        f"Error while calling local API endpoint {path}."
                    ) from ex

                _LOGGER.debug(
                    "Error while calling local API endpoint %s, retrying with cloud call. Error: %s",
                    path,
                    type(ex).__name__,
                )
                _LOGGER.debug("Full error: %s", str(ex), exc_info=True)
        return False, None

    def parse_webhook_message(self, message: dict) -> None:
        """Parse the webhook message sent from the bridge"""

        message_type = message.get("event")
        data = message.get("data")

        if data is None:
            raise TedeeWebhookException("No data in webhook message.")

        if message_type == "backend-connection-changed":
            return

        lock_id = data.get("deviceId", 0)
        lock = self._locks_dict.get(lock_id)

        if lock is None:
            return

        if message_type == "device-connection-changed":
            lock.is_connected = data.get("isConnected", 0) == 1
        elif message_type == "device-settings-changed":
            pass
        elif message_type == "lock-status-changed":
            lock.state = data.get("state", 0)
            lock.state_change_result = data.get("jammed", 0)
        elif message_type == "device-battery-level-changed":
            lock.battery_level = data.get("batteryLevel", 50)
        elif message_type == "device-battery-start-charging":
            lock.is_charging = True
        elif message_type == "device-battery-stop-charging":
            lock.is_charging = False
        elif message_type == "device-battery-fully-charged":
            lock.is_charging = False
            lock.battery_level = 100

        self._locks_dict[lock_id] = lock

    async def update_webhooks(
        self, webhook_url: str, headers_bridge_sends: list | None = None
    ) -> None:
        """Overrites all webhooks"""
        if headers_bridge_sends is None:
            headers_bridge_sends = []
        _LOGGER.debug("Registering webhook %s", webhook_url)
        data = [{"url": webhook_url, "headers": headers_bridge_sends}]
        await self._local_api_call("/callback", HTTPMethod.PUT, data)
        _LOGGER.debug("Webhook registered successfully.")

    async def register_webhook(
        self, webhook_url: str, headers_bridge_sends: list | None = None
    ) -> int:
        """Register a webhook, return the webhook id"""
        if headers_bridge_sends is None:
            headers_bridge_sends = []
        _LOGGER.debug("Registering webhook %s", webhook_url)
        data = {"url": webhook_url, "headers": headers_bridge_sends}
        try:
            success, result = await self._local_api_call("/callback", "POST", data)
        except TedeeDataUpdateException as ex:
            raise TedeeWebhookException("Unable to register webhook") from ex
        if not success:
            raise TedeeWebhookException("Unable to register webhook")
        _LOGGER.debug("Webhook registered successfully.")
        # get the webhook id
        try:
            success, result = await self._local_api_call("/callback", HTTPMethod.GET)
        except TedeeDataUpdateException as ex:
            raise TedeeWebhookException("Unable to get webhooks") from ex
        if not success or result is None:
            raise TedeeWebhookException("Unable to get webhooks")
        for webhook in result:
            if webhook["url"] == webhook_url:
                return webhook["id"]
        raise TedeeWebhookException("Webhook id not found")

    async def delete_webhooks(self) -> None:
        """Delete all webhooks"""
        _LOGGER.debug("Deleting webhooks...")
        try:
            await self._local_api_call("/callback", "PUT", [])
        except TedeeDataUpdateException as ex:
            _LOGGER.debug("Unable to delete webhooks: %s", str(ex))
        _LOGGER.debug("Webhooks deleted successfully.")

    async def delete_webhook(self, webhook_id: int) -> None:
        """Delete a specific webhook"""
        _LOGGER.debug("Deleting webhook %s", str(webhook_id))
        try:
            await self._local_api_call(f"/callback/{webhook_id}", HTTPMethod.DELETE)
        except TedeeDataUpdateException as ex:
            _LOGGER.debug("Unable to delete webhook: %s", str(ex))
        _LOGGER.debug("Webhook deleted successfully.")
