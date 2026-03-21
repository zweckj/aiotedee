"""Tests for aiotedee models."""

from __future__ import annotations

from aiotedee.models import (
    TedeeBridge,
    TedeeDoorState,
    TedeeLock,
    TedeeLockState,
    _safe_door_state,
    _safe_lock_state,
)

from .conftest import BRIDGE_JSON, LOCK_CLOUD_JSON, LOCK_LOCAL_JSON


# -- Safe enum conversion -----------------------------------------------------


class TestSafeEnumConversion:
    """_safe_lock_state / _safe_door_state handle unknown API values."""

    def test_safe_lock_state_known(self):
        assert _safe_lock_state(6) == TedeeLockState.LOCKED

    def test_safe_lock_state_unknown_falls_back(self):
        assert _safe_lock_state(999) == TedeeLockState.UNKNOWN

    def test_safe_door_state_known(self):
        assert _safe_door_state(3) == TedeeDoorState.CLOSED

    def test_safe_door_state_unknown_falls_back(self):
        assert _safe_door_state(999) == TedeeDoorState.NOT_PAIRED


# -- TedeeLock.from_api_response -----------------------------------------------


class TestTedeeLockFromApiResponse:
    """Parsing lock data from cloud and local API formats."""

    def test_cloud_format(self):
        """Cloud API nests state under lockProperties."""
        lock = TedeeLock.from_api_response(LOCK_CLOUD_JSON)

        assert lock.id == 12345
        assert lock.name == "Front Door"
        assert lock.type == 2
        assert lock.type_name == "Tedee PRO"
        assert lock.state == TedeeLockState.LOCKED
        assert lock.battery_level == 80
        assert lock.is_connected is True
        assert lock.is_charging is False
        assert lock.state_change_result == 0
        assert lock.door_state == TedeeDoorState.CLOSED
        assert lock.is_enabled_pullspring is True
        assert lock.is_enabled_auto_pullspring is False
        assert lock.duration_pullspring == 7

    def test_local_format(self):
        """Local API places state at the top level, uses 'jammed' key."""
        lock = TedeeLock.from_api_response(LOCK_LOCAL_JSON)

        assert lock.state == TedeeLockState.LOCKED
        assert lock.battery_level == 80
        assert lock.state_change_result == 0  # from "jammed"
        assert lock.door_state == TedeeDoorState.CLOSED

    def test_unknown_lock_type_name(self):
        data = {**LOCK_CLOUD_JSON, "type": 999}
        lock = TedeeLock.from_api_response(data)
        assert lock.type_name == "Unknown Model"

    def test_missing_optional_fields_use_defaults(self):
        """Minimal payload still parses without errors."""
        data = {"id": 1, "name": "Minimal"}
        lock = TedeeLock.from_api_response(data)

        assert lock.id == 1
        assert lock.type == 0
        assert lock.state == TedeeLockState.UNKNOWN
        assert lock.battery_level is None
        assert lock.is_connected is False
        assert lock.duration_pullspring == 5  # DEFAULT_PULLSPRING_DURATION

    def test_jammed_state_from_cloud(self):
        """Cloud uses stateChangeResult for jammed detection."""
        data = {**LOCK_CLOUD_JSON}
        data["lockProperties"] = {**data["lockProperties"], "stateChangeResult": 1}
        lock = TedeeLock.from_api_response(data)
        assert lock.is_jammed is True

    def test_jammed_state_from_local(self):
        """Local API uses 'jammed' key."""
        data = {**LOCK_LOCAL_JSON, "jammed": 1}
        lock = TedeeLock.from_api_response(data)
        assert lock.is_jammed is True


# -- TedeeLock.update_from_api_response ----------------------------------------


class TestTedeeLockUpdate:
    """In-place updates from sync responses."""

    def test_updates_state_fields(self, sample_lock):
        """Sync response updates state but not settings by default."""
        sync_data = {
            "id": 12345,
            "isConnected": False,
            "lockProperties": {
                "state": 2,  # UNLOCKED
                "batteryLevel": 75,
                "isCharging": True,
                "stateChangeResult": 0,
                "doorState": 2,  # OPENED
            },
        }
        sample_lock.update_from_api_response(sync_data)

        assert sample_lock.state == TedeeLockState.UNLOCKED
        assert sample_lock.battery_level == 75
        assert sample_lock.is_connected is False
        assert sample_lock.is_charging is True
        assert sample_lock.door_state == TedeeDoorState.OPENED
        # Settings NOT updated without include_settings
        assert sample_lock.is_enabled_pullspring is True
        assert sample_lock.duration_pullspring == 7

    def test_include_settings_updates_pullspring(self, sample_lock):
        """Local sync includes deviceSettings."""
        sync_data = {
            "id": 12345,
            "isConnected": True,
            "state": 6,
            "batteryLevel": 80,
            "isCharging": False,
            "jammed": 0,
            "doorState": 3,
            "deviceSettings": {
                "pullSpringEnabled": False,
                "autoPullSpringEnabled": True,
                "pullSpringDuration": 3,
            },
        }
        sample_lock.update_from_api_response(sync_data, include_settings=True)

        assert sample_lock.is_enabled_pullspring is False
        assert sample_lock.is_enabled_auto_pullspring is True
        assert sample_lock.duration_pullspring == 3


# -- TedeeLock computed properties ---------------------------------------------


class TestTedeeLockProperties:
    def test_is_locked(self):
        lock = TedeeLock(name="L", id=1, type=2, state=TedeeLockState.LOCKED)
        assert lock.is_locked is True
        assert lock.is_unlocked is False

    def test_is_unlocked(self):
        lock = TedeeLock(name="L", id=1, type=2, state=TedeeLockState.UNLOCKED)
        assert lock.is_locked is False
        assert lock.is_unlocked is True

    def test_intermediate_states_are_neither(self):
        lock = TedeeLock(name="L", id=1, type=2, state=TedeeLockState.LOCKING)
        assert lock.is_locked is False
        assert lock.is_unlocked is False

    def test_is_jammed(self):
        lock = TedeeLock(name="L", id=1, type=2, state_change_result=1)
        assert lock.is_jammed is True

    def test_is_not_jammed(self):
        lock = TedeeLock(name="L", id=1, type=2, state_change_result=0)
        assert lock.is_jammed is False


# -- TedeeBridge.from_api_response ---------------------------------------------


class TestTedeeBridge:
    def test_from_api_response(self):
        bridge = TedeeBridge.from_api_response(BRIDGE_JSON)
        assert bridge.id == 99
        assert bridge.serial == "12345678-0001"
        assert bridge.name == "My Bridge"

    def test_missing_id_defaults_to_zero(self):
        data = {"serialNumber": "SN", "name": "B"}
        bridge = TedeeBridge.from_api_response(data)
        assert bridge.id == 0
