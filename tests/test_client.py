"""Tests for the client hierarchy: local and cloud clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession

from aiotedee import (
    TedeeClientException,
    TedeeLock,
    TedeeLockState,
    TedeeWebhookException,
)
from aiotedee.client import TedeeCloudClient, TedeeLocalClient
from aiotedee.const import API_URL_BRIDGE, API_URL_LOCK, API_URL_SYNC
from aiotedee.exceptions import TedeeDataUpdateException

from .conftest import BRIDGE_JSON, LOCAL_API_BASE, LOCK_CLOUD_JSON, LOCK_LOCAL_JSON


@pytest.fixture(autouse=True)
def _no_sleep():
    """Prevent real asyncio.sleep delays in lock operations."""
    with patch("aiotedee.client.asyncio.sleep", new_callable=AsyncMock):
        yield


# =============================================================================
# Base / shared behaviour (tested via TedeeLocalClient)
# =============================================================================


@pytest.mark.parametrize(
    ("bridge_id", "locks", "expected_ids"),
    [
        (None, [{"connectedToId": 1}, {"connectedToId": 2}], [1, 2]),
        (1, [{"connectedToId": 1}, {"connectedToId": 2}], [1]),
        (1, [{"connectedToId": None}, {"connectedToId": 2}], [None]),
    ],
    ids=["no-filter", "filter-matching", "null-passes-through"],
)
def test_filter_by_bridge(local_client, bridge_id, locks, expected_ids):
    local_client._bridge_id = bridge_id
    result = local_client._filter_by_bridge(locks)
    assert [l["connectedToId"] for l in result] == expected_ids


def test_webhook_dispatches_lock_status_changed(local_client):
    local_client._locks[1] = TedeeLock(
        name="L", id=1, type=2, state=TedeeLockState.LOCKED
    )
    local_client.parse_webhook_message({
        "event": "lock-status-changed",
        "data": {"deviceId": 1, "state": 2, "jammed": 0, "doorState": 3},
    })
    assert local_client._locks[1].state == TedeeLockState.UNLOCKED


def test_webhook_missing_data_raises(local_client):
    with pytest.raises(TedeeWebhookException):
        local_client.parse_webhook_message({"event": "lock-status-changed"})


@pytest.mark.parametrize(
    ("event", "data"),
    [
        ("backend-connection-changed", {}),
        ("lock-status-changed", {"deviceId": 999, "state": 2}),
        ("some-future-event", {"deviceId": 1}),
    ],
    ids=["backend-connection", "unknown-device", "unknown-event"],
)
def test_webhook_silently_ignored_messages(local_client, event, data):
    local_client._locks[1] = TedeeLock(
        name="L", id=1, type=2, state=TedeeLockState.LOCKED
    )
    local_client.parse_webhook_message({"event": event, "data": data})
    assert local_client._locks[1].state == TedeeLockState.LOCKED


# =============================================================================
# TedeeLocalClient
# =============================================================================


async def test_local_get_locks(mock_api, local_client):
    mock_api.get(f"{LOCAL_API_BASE}/lock", payload=[LOCK_LOCAL_JSON])
    await local_client.get_locks()
    assert 12345 in local_client.locks_dict
    assert local_client.locks_dict[12345].name == "Front Door"


async def test_local_get_locks_empty_raises(mock_api, local_client):
    mock_api.get(f"{LOCAL_API_BASE}/lock", payload=[])
    with pytest.raises(TedeeClientException, match="No lock found"):
        await local_client.get_locks()


async def test_local_sync_updates_existing_lock(mock_api, local_client):
    local_client._locks[12345] = TedeeLock(
        name="Front Door", id=12345, type=2, state=TedeeLockState.LOCKED
    )
    mock_api.get(
        f"{LOCAL_API_BASE}/lock",
        payload=[{**LOCK_LOCAL_JSON, "state": 2}],
    )
    await local_client.sync()
    assert local_client._locks[12345].state == TedeeLockState.UNLOCKED


async def test_local_sync_includes_settings(mock_api, local_client):
    """Local sync passes include_settings=True, updating deviceSettings."""
    local_client._locks[12345] = TedeeLock(
        name="Front Door", id=12345, type=2, is_enabled_pullspring=True
    )
    updated = {
        **LOCK_LOCAL_JSON,
        "deviceSettings": {
            "pullSpringEnabled": False,
            "autoPullSpringEnabled": True,
            "pullSpringDuration": 3,
        },
    }
    mock_api.get(f"{LOCAL_API_BASE}/lock", payload=[updated])
    await local_client.sync()
    assert local_client._locks[12345].is_enabled_pullspring is False


async def test_local_sync_skips_unknown_lock_ids(mock_api, local_client):
    local_client._locks[1] = TedeeLock(name="L", id=1, type=2)
    mock_api.get(
        f"{LOCAL_API_BASE}/lock",
        payload=[{"id": 9999, "state": 2}],
    )
    await local_client.sync()
    assert 9999 not in local_client._locks


@pytest.mark.parametrize(
    ("method", "expected_path"),
    [
        ("lock", "/lock/1/lock"),
        ("unlock", "/lock/1/unlock?mode=3"),
        ("open", "/lock/1/unlock?mode=4"),
        ("pull", "/lock/1/pull"),
    ],
    ids=["lock", "unlock", "open", "pull"],
)
async def test_local_lock_operations(mock_api, local_client, method, expected_path):
    local_client._locks[1] = TedeeLock(
        name="L", id=1, type=2, duration_pullspring=4
    )
    mock_api.post(f"{LOCAL_API_BASE}{expected_path}", payload=None)
    await getattr(local_client, method)(1)


async def test_local_lock_operation_failure_raises(mock_api, local_client):
    local_client._locks[1] = TedeeLock(name="L", id=1, type=2)
    # _local_api_call retries NUM_RETRIES(3) times, then wraps in TedeeDataUpdateException
    for _ in range(3):
        mock_api.post(f"{LOCAL_API_BASE}/lock/1/lock", status=500)
    with pytest.raises(TedeeDataUpdateException):
        await local_client.lock(1)


async def test_local_get_bridge(mock_api, local_client):
    mock_api.get(f"{LOCAL_API_BASE}/bridge", payload=BRIDGE_JSON)
    bridge = await local_client.get_local_bridge()
    assert bridge.id == 99
    assert bridge.serial == "12345678-0001"


async def test_local_get_bridge_not_configured_raises():
    session = ClientSession()
    client = TedeeLocalClient(
        local_token="", local_ip="", session=session
    )
    with pytest.raises(TedeeClientException, match="Local API not configured"):
        await client.get_local_bridge()
    await session.close()


@pytest.mark.parametrize(
    ("plain_mode", "token_value"),
    [(True, "tok"), (False, None)],
    ids=["plain", "hashed"],
)
def test_local_api_header_token_mode(local_client, plain_mode, token_value):
    local_client._api_token_mode_plain = plain_mode
    header = local_client._local_api_header
    if token_value:
        assert header["api_token"] == token_value
    else:
        # Hashed mode: sha256hex + timestamp digits → always > 64 chars
        assert len(header["api_token"]) > 64


async def test_local_api_header_no_token_returns_empty():
    session = ClientSession()
    client = TedeeLocalClient(
        local_token="", local_ip="192.168.1.1", session=session
    )
    assert client._local_api_header == {}
    await session.close()


# =============================================================================
# TedeeCloudClient
# =============================================================================


async def test_cloud_get_locks(mock_api, cloud_client):
    mock_api.get(API_URL_LOCK, payload={"result": [LOCK_CLOUD_JSON]})
    await cloud_client.get_locks()
    assert 12345 in cloud_client.locks_dict


async def test_cloud_get_locks_bridge_filter(mock_api):
    session = ClientSession()
    client = TedeeCloudClient(
        personal_token="cloud-key", bridge_id=99, session=session
    )
    other_lock = {**LOCK_CLOUD_JSON, "id": 99999, "connectedToId": 50}
    mock_api.get(API_URL_LOCK, payload={"result": [LOCK_CLOUD_JSON, other_lock]})
    await client.get_locks()
    assert 12345 in client.locks_dict
    assert 99999 not in client.locks_dict
    await session.close()


async def test_cloud_sync_does_not_include_settings(mock_api, cloud_client):
    """Cloud sync passes include_settings=False."""
    cloud_client._locks[12345] = TedeeLock(
        name="Front Door",
        id=12345,
        type=2,
        is_enabled_pullspring=True,
        duration_pullspring=7,
    )
    sync_response = {
        "id": 12345,
        "isConnected": True,
        "lockProperties": {
            "state": 2,
            "batteryLevel": 60,
            "isCharging": False,
            "stateChangeResult": 0,
            "doorState": 3,
        },
        "deviceSettings": {
            "pullSpringEnabled": False,
            "autoPullSpringEnabled": True,
            "pullSpringDuration": 1,
        },
    }
    mock_api.get(API_URL_SYNC, payload={"result": [sync_response]})
    await cloud_client.sync()
    assert cloud_client._locks[12345].state == TedeeLockState.UNLOCKED
    # Settings NOT updated (cloud sync)
    assert cloud_client._locks[12345].is_enabled_pullspring is True
    assert cloud_client._locks[12345].duration_pullspring == 7


async def test_cloud_get_bridges(mock_api, cloud_client):
    mock_api.get(API_URL_BRIDGE, payload={"result": [BRIDGE_JSON]})
    bridges = await cloud_client.get_bridges()
    assert len(bridges) == 1
    assert bridges[0].id == 99


async def test_cloud_lock_sends_correct_url(mock_api, cloud_client):
    cloud_client._locks[1] = TedeeLock(name="L", id=1, type=2)
    mock_api.post(f"{API_URL_LOCK}1/operation/lock", payload=None)
    await cloud_client.lock(1)
