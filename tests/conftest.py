"""Shared fixtures for aiotedee tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aiohttp import ClientSession

from aiotedee import TedeeLock, TedeeLockState


# -- Fake API response payloads ------------------------------------------------

LOCK_CLOUD_JSON = {
    "id": 12345,
    "name": "Front Door",
    "type": 2,
    "isConnected": True,
    "connectedToId": 99,
    "lockProperties": {
        "state": 6,  # LOCKED
        "batteryLevel": 80,
        "isCharging": False,
        "stateChangeResult": 0,
        "doorState": 3,  # CLOSED
    },
    "deviceSettings": {
        "pullSpringEnabled": True,
        "autoPullSpringEnabled": False,
        "pullSpringDuration": 7,
    },
}

LOCK_LOCAL_JSON = {
    "id": 12345,
    "name": "Front Door",
    "type": 2,
    "isConnected": True,
    "connectedToId": 99,
    "state": 6,
    "batteryLevel": 80,
    "isCharging": False,
    "jammed": 0,
    "doorState": 3,
    "deviceSettings": {
        "pullSpringEnabled": True,
        "autoPullSpringEnabled": False,
        "pullSpringDuration": 7,
    },
}

BRIDGE_JSON = {
    "id": 99,
    "serialNumber": "12345678-0001",
    "name": "My Bridge",
}


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Return a mock aiohttp ClientSession."""
    return MagicMock(spec=ClientSession)


@pytest.fixture
def sample_lock():
    """Return a TedeeLock with typical test values."""
    return TedeeLock(
        name="Front Door",
        id=12345,
        type=2,
        state=TedeeLockState.LOCKED,
        battery_level=80,
        is_connected=True,
        is_charging=False,
        state_change_result=0,
        is_enabled_pullspring=True,
        is_enabled_auto_pullspring=False,
        duration_pullspring=7,
    )
