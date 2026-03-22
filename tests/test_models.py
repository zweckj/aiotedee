"""Tests for aiotedee models."""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (6, TedeeLockState.LOCKED),
        (2, TedeeLockState.UNLOCKED),
        (0, TedeeLockState.UNCALIBRATED),
        (999, TedeeLockState.UNKNOWN),
        (-1, TedeeLockState.UNKNOWN),
    ],
    ids=["locked", "unlocked", "uncalibrated", "unknown-high", "unknown-negative"],
)
def test_safe_lock_state(value, expected):
    assert _safe_lock_state(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (3, TedeeDoorState.CLOSED),
        (2, TedeeDoorState.OPENED),
        (999, TedeeDoorState.NOT_PAIRED),
        (-1, TedeeDoorState.NOT_PAIRED),
    ],
    ids=["closed", "opened", "unknown-high", "unknown-negative"],
)
def test_safe_door_state(value, expected):
    assert _safe_door_state(value) == expected


# -- TedeeLock.from_api_response -----------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [LOCK_CLOUD_JSON, LOCK_LOCAL_JSON],
    ids=["cloud", "local"],
)
def test_from_api_response(payload):
    """Both cloud and local payloads parse all fields correctly."""
    lock = TedeeLock.from_api_response(payload)

    # Core fields
    assert lock.id == 12345
    assert lock.name == "Front Door"
    assert lock.type == 2
    assert lock.state == TedeeLockState.LOCKED
    assert lock.battery_level == 80
    assert lock.is_connected is True

    # Pullspring settings
    assert lock.is_enabled_pullspring is True
    assert lock.is_enabled_auto_pullspring is False
    assert lock.duration_pullspring == 7

    # Not jammed (stateChangeResult=0 / jammed=0)
    assert lock.is_jammed is False


@pytest.mark.parametrize(
    ("payload", "jammed_key"),
    [
        (LOCK_CLOUD_JSON, "stateChangeResult"),
        (LOCK_LOCAL_JSON, "jammed"),
    ],
    ids=["cloud-stateChangeResult", "local-jammed"],
)
def test_from_api_response_detects_jammed(payload, jammed_key):
    """Cloud uses stateChangeResult=1, local uses jammed=1 — both detected."""
    if "lockProperties" in payload:
        modified = {**payload, "lockProperties": {**payload["lockProperties"], jammed_key: 1}}
    else:
        modified = {**payload, jammed_key: 1}
    lock = TedeeLock.from_api_response(modified)
    assert lock.is_jammed is True


@pytest.mark.parametrize(
    ("type_id", "expected_name"),
    [(2, "Tedee PRO"), (4, "Tedee GO"), (999, "Unknown Model")],
    ids=["pro", "go", "unknown"],
)
def test_lock_type_names(type_id, expected_name):
    lock = TedeeLock.from_api_response({**LOCK_CLOUD_JSON, "type": type_id})
    assert lock.type_name == expected_name


def test_missing_optional_fields_use_defaults():
    """Minimal payload still parses without errors."""
    lock = TedeeLock.from_api_response({"id": 1, "name": "Minimal"})
    assert lock.type == 0
    assert lock.state == TedeeLockState.UNKNOWN
    assert lock.battery_level is None
    assert lock.is_connected is False
    assert lock.duration_pullspring == 5  # DEFAULT_PULLSPRING_DURATION


# -- TedeeLock.update_from_api_response ----------------------------------------


def test_update_changes_state_fields(sample_lock):
    """Sync response updates state but not settings by default."""
    sample_lock.update_from_api_response(
        {
            "id": 12345,
            "isConnected": False,
            "lockProperties": {
                "state": 2,
                "batteryLevel": 75,
                "isCharging": True,
                "stateChangeResult": 0,
                "doorState": 2,
            },
        }
    )
    assert sample_lock.state == TedeeLockState.UNLOCKED
    assert sample_lock.battery_level == 75
    assert sample_lock.is_connected is False
    assert sample_lock.is_charging is True
    assert sample_lock.door_state == TedeeDoorState.OPENED
    # Settings NOT updated without include_settings
    assert sample_lock.is_enabled_pullspring is True
    assert sample_lock.duration_pullspring == 7


def test_update_with_include_settings(sample_lock):
    """Local sync includes deviceSettings."""
    sample_lock.update_from_api_response(
        {
            **LOCK_LOCAL_JSON,
            "deviceSettings": {
                "pullSpringEnabled": False,
                "autoPullSpringEnabled": True,
                "pullSpringDuration": 3,
            },
        },
        include_settings=True,
    )
    assert sample_lock.is_enabled_pullspring is False
    assert sample_lock.is_enabled_auto_pullspring is True
    assert sample_lock.duration_pullspring == 3


# -- TedeeLock computed properties ---------------------------------------------


@pytest.mark.parametrize(
    ("state", "is_locked", "is_unlocked"),
    [
        (TedeeLockState.LOCKED, True, False),
        (TedeeLockState.UNLOCKED, False, True),
        (TedeeLockState.LOCKING, False, False),
        (TedeeLockState.PULLING, False, False),
    ],
    ids=["locked", "unlocked", "locking", "pulling"],
)
def test_lock_state_properties(state, is_locked, is_unlocked):
    lock = TedeeLock(name="L", id=1, type=2, state=state)
    assert lock.is_locked is is_locked
    assert lock.is_unlocked is is_unlocked


@pytest.mark.parametrize(
    ("state_change_result", "expected"),
    [(0, False), (1, True), (2, False)],
    ids=["not-jammed", "jammed", "other-value"],
)
def test_is_jammed(state_change_result, expected):
    lock = TedeeLock(name="L", id=1, type=2, state_change_result=state_change_result)
    assert lock.is_jammed is expected


# -- TedeeBridge.from_api_response ---------------------------------------------


def test_bridge_from_api_response():
    bridge = TedeeBridge.from_api_response(BRIDGE_JSON)
    assert bridge.id == 99
    assert bridge.serial == "12345678-0001"
    assert bridge.name == "My Bridge"


def test_bridge_missing_id_defaults_to_zero():
    bridge = TedeeBridge.from_api_response({"serialNumber": "SN", "name": "B"})
    assert bridge.id == 0
