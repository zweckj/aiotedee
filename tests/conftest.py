"""Shared fixtures for aiotedee tests."""

from __future__ import annotations

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from aiotedee import TedeeLock, TedeeLockState
from aiotedee.client import TedeeCloudClient, TedeeLocalClient


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

LOCAL_API_BASE = "http://192.168.1.1:80/v1.0"


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def mock_api():
    """Yield an aioresponses context for mocking aiohttp calls."""
    with aioresponses() as m:
        yield m


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


@pytest.fixture
async def local_client():
    """Return a TedeeLocalClient with a real aiohttp session."""
    session = ClientSession()
    client = TedeeLocalClient(
        local_token="tok",
        local_ip="192.168.1.1",
        session=session,
    )
    yield client
    await session.close()


@pytest.fixture
async def cloud_client():
    """Return a TedeeCloudClient with a real aiohttp session."""
    session = ClientSession()
    client = TedeeCloudClient(
        personal_token="cloud-key",
        session=session,
    )
    yield client
    await session.close()
