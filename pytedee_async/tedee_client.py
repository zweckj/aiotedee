"""The TedeeClient class."""
import logging
import asyncio
import hashlib
import time

from .const import (
    API_URL_LOCK,
    API_PATH_UNLOCK,
    API_PATH_LOCK,
    API_PATH_PULL,
    API_URL_SYNC,
    API_LOCAL_PORT,
    API_LOCAL_VERSION,
    TIMEOUT,
    UNLOCK_DELAY,
    LOCK_DELAY,
)

from .helpers import http_request
from .lock import TedeeLock
from .exception import (
    TedeeClientException,
    TedeeAuthException,
    TedeeLocalAuthException,
    TedeeDataUpdateException,
    TedeeWebhookException,
)


_LOGGER = logging.getLogger(__name__)


class TedeeClient(object):
    """Classdocs"""

    def __init__(
        self,
        personal_token: str = None,
        local_token: str = None,
        local_ip: str = None,
        timeout: int = TIMEOUT,
    ):
        """Constructor"""
        self._available = False
        self._personal_token = personal_token
        self._locks_dict: dict[int, TedeeLock] = {}
        self._local_token = local_token
        self._local_ip = local_ip
        self._timeout = timeout
        self._use_local_api = local_token is not None and local_ip is not None

        _LOGGER.debug("Using local API: %s", str(self._use_local_api))

        # Create the api header with new token"
        self._api_header = {
            "Content-Type": "application/json",
            "Authorization": "PersonalKey " + str(self._personal_token),
        }
        self._local_api_path = f"http://{local_ip}:{API_LOCAL_PORT}/{API_LOCAL_VERSION}"

    @classmethod
    async def create(
        cls,
        personal_token: str = None,
        local_token: str = None,
        local_ip: str = None,
        timeout=TIMEOUT,
    ):
        """Create a new instance of the TedeeClient, which is initialized."""
        self = cls(personal_token, local_token, local_ip, timeout)
        await self.get_locks()
        return self

    @property
    def locks(self):
        """Return a list of locks"""
        return self._locks_dict.values()

    @property
    def locks_dict(self) -> dict:
        """Return all locks."""
        return self._locks_dict

    async def get_locks(self) -> None:
        """Get the list of registered locks"""
        local_call_success, result = await self._local_api_call("/lock", "GET")
        if not local_call_success:
            r = await http_request(API_URL_LOCK, "GET", self._api_header, self._timeout)
            result = r["result"]
        _LOGGER.debug("Locks %s", result)

        for lock_json in result:
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
        _LOGGER.debug("Syncing locks...")
        local_call_success, result = await self._local_api_call("/lock", "GET")
        if not local_call_success:
            r = await http_request(API_URL_SYNC, "GET", self._api_header, self._timeout)
            result = r["result"]

        for lock_json in result:
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
        _LOGGER.debug("Locks synced successfully...")

    async def unlock(self, lock_id: int) -> None:
        """Unlock method"""
        _LOGGER.debug("Unlocking lock %s...", str(lock_id))
        local_call_success, _ = await self._local_api_call(
            f"/lock/{lock_id}/unlock?mode=3", "POST"
        )
        if not local_call_success:
            url = API_URL_LOCK + str(lock_id) + API_PATH_UNLOCK + "?mode=3"
            await http_request(url, "POST", self._api_header, self._timeout)
        _LOGGER.debug("unlock command successful, id: %d ", lock_id)
        await asyncio.sleep(UNLOCK_DELAY)

    async def lock(self, lock_id: int) -> None:
        """'Lock method"""
        _LOGGER.debug("Locking lock %s...", str(lock_id))
        local_call_success, _ = await self._local_api_call(
            f"/lock/{lock_id}/lock", "POST"
        )
        if not local_call_success:
            url = API_URL_LOCK + str(lock_id) + API_PATH_LOCK
            await http_request(url, "POST", self._api_header, self._timeout)
        _LOGGER.debug("lock command successful, id: %s", lock_id)
        await asyncio.sleep(LOCK_DELAY)

    # pulling
    async def open(self, lock_id: int) -> None:
        """Unlock the door and pull the door latch"""
        _LOGGER.debug("Opening lock %s...", str(lock_id))
        local_call_success, _ = await self._local_api_call(
            f"/lock/{lock_id}/unlock?mode=4", "POST"
        )
        if not local_call_success:
            url = API_URL_LOCK + str(lock_id) + API_PATH_UNLOCK + "?mode=4"
            await http_request(url, "POST", self._api_header, self._timeout)
        _LOGGER.debug("Open command successful, id: %s", lock_id)
        await asyncio.sleep(self._locks_dict[lock_id].duration_pullspring + 1)

    async def pull(self, lock_id: int) -> None:
        """Only pull the door latch"""
        _LOGGER.debug("Pulling latch for lock %s...", str(lock_id))
        local_call_success, _ = await self._local_api_call(
            f"/lock/{lock_id}/pull", "POST"
        )
        if not local_call_success:
            url = API_URL_LOCK + str(lock_id) + API_PATH_PULL
            await http_request(url, "POST", self._api_header, self._timeout)
        _LOGGER.debug("Open command not successful, id: %s", lock_id)
        await asyncio.sleep(self._locks_dict[lock_id].duration_pullspring + 1)

    def is_unlocked(self, lock_id: int) -> bool:
        """Return is a specific lock is unlocked"""
        lock = self._locks_dict[lock_id]
        return lock.state == 2

    def is_locked(self, lock_id: int) -> bool:
        """Return is a specific lock is locked"""
        lock = self._locks_dict[lock_id]
        return lock.state == 6

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
        pull_spring_enabled = device_settings.get("pullSpringEnabled", False)
        pull_spring_duration = device_settings.get("pullSpringDuration", 5)
        return pull_spring_enabled, pull_spring_duration

    def _calculate_secure_local_token(self) -> str:
        """Calculate the secure token"""
        ms = time.time_ns() // 1_000_000
        secure_token = self._local_token + str(ms)
        secure_token = hashlib.sha256(secure_token.encode("utf-8")).hexdigest()
        secure_token += str(ms)
        return secure_token

    def _get_local_api_header(self, secure: bool = True) -> str:
        """Get the local api header"""
        token = self._calculate_secure_local_token() if secure else self._local_token
        return {"Content-Type": "application/json", "api_token": token}

    async def _local_api_call(self, path: str, http_method: str, json_data=None):
        """Call the local api"""
        if self._use_local_api:
            try:
                _LOGGER.debug("Getting locks from Local API...")
                r = await http_request(
                    self._local_api_path + path,
                    http_method,
                    self._get_local_api_header(),
                    self._timeout,
                    json_data,
                )
                return True, r
            except TedeeAuthException as ex:
                msg = "Local API authentication failed."
                if not self._personal_token:
                    raise TedeeLocalAuthException(msg) from ex
                else:
                    _LOGGER.debug(msg)
            except Exception as ex:
                if not self._personal_token:
                    _LOGGER.debug(
                        "Error while calling local API endpoint %s. Error: %s. Full error: %s",
                        path,
                        {type(ex).__name__},
                        str(ex),
                        exc_info=1,
                    )
                    raise TedeeDataUpdateException(
                        f"Error while calling local API endpoint {path}."
                    ) from ex
                else:
                    _LOGGER.debug(
                        "Error while calling local API endpoint %s, retrying with cloud call. Error: %s",
                        path,
                        type(ex).__name__,
                    )
                _LOGGER.debug("Full error: %s", str(ex), exc_info=1)
        return False, None

    def parse_webhook_message(self, message: dict) -> None:
        """Parse the webhook message sent from the bridge"""

        message_type = message.get("type")
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

    async def register_webhook(self, webhook_url: str, headers: list = None) -> None:
        """Register the webhook"""
        if headers is None:
            headers = []
        _LOGGER.debug("Registering webhook %s", webhook_url)
        data = [{"url": webhook_url, "headers": headers}]
        await self._local_api_call("/callback", "PUT", data)
        _LOGGER.debug("Webhook registered successfully.")

    async def delete_webhooks(self) -> None:
        """Delete all webhooks"""
        _LOGGER.debug("Deleting webhooks...")
        await self._local_api_call("/callback", "PUT", [])
        _LOGGER.debug("Webhooks deleted successfully.")
