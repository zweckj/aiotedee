"""Tests for the client hierarchy: local and cloud clients."""

from __future__ import annotations

from http import HTTPMethod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession

from aiotedee import (
    TedeeClientException,
    TedeeLock,
    TedeeLockState,
    TedeeWebhookException,
)
from aiotedee.client import TedeeCloudClient, TedeeLocalClient

from .conftest import BRIDGE_JSON, LOCK_CLOUD_JSON, LOCK_LOCAL_JSON


# -- Helpers -------------------------------------------------------------------


def _make_local_client(mock_session, **overrides):
    defaults = dict(local_token="tok", local_ip="192.168.1.1", session=mock_session)
    defaults.update(overrides)
    return TedeeLocalClient(**defaults)


def _make_cloud_client(mock_session, **overrides):
    defaults = dict(personal_token="cloud-key", session=mock_session)
    defaults.update(overrides)
    return TedeeCloudClient(**defaults)


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
def test_filter_by_bridge(mock_session, bridge_id, locks, expected_ids):
    client = _make_local_client(mock_session, bridge_id=bridge_id)
    result = client._filter_by_bridge(locks)
    assert [l["connectedToId"] for l in result] == expected_ids


def test_webhook_dispatches_lock_status_changed(mock_session):
    client = _make_local_client(mock_session)
    client._locks[1] = TedeeLock(
        name="L", id=1, type=2, state=TedeeLockState.LOCKED
    )
    client.parse_webhook_message({
        "event": "lock-status-changed",
        "data": {"deviceId": 1, "state": 2, "jammed": 0, "doorState": 3},
    })
    assert client._locks[1].state == TedeeLockState.UNLOCKED


def test_webhook_missing_data_raises(mock_session):
    client = _make_local_client(mock_session)
    with pytest.raises(TedeeWebhookException):
        client.parse_webhook_message({"event": "lock-status-changed"})


@pytest.mark.parametrize(
    ("event", "data"),
    [
        ("backend-connection-changed", {}),
        ("lock-status-changed", {"deviceId": 999, "state": 2}),
        ("some-future-event", {"deviceId": 1}),
    ],
    ids=["backend-connection", "unknown-device", "unknown-event"],
)
def test_webhook_silently_ignored_messages(mock_session, event, data):
    client = _make_local_client(mock_session)
    client._locks[1] = TedeeLock(
        name="L", id=1, type=2, state=TedeeLockState.LOCKED
    )
    client.parse_webhook_message({"event": event, "data": data})
    assert client._locks[1].state == TedeeLockState.LOCKED


# =============================================================================
# TedeeLocalClient
# =============================================================================


async def test_local_get_locks_success(mock_session):
    client = _make_local_client(mock_session)
    with patch.object(
        client, "_local_api_call", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = (True, [LOCK_LOCAL_JSON])
        await client.get_locks()
    assert 12345 in client.locks_dict
    assert client.locks_dict[12345].name == "Front Door"


@pytest.mark.parametrize(
    ("return_value", "match"),
    [
        ((False, None), "No data returned from local API"),
        ((True, []), "No lock found"),
    ],
    ids=["api-failure", "empty-result"],
)
async def test_local_get_locks_failure(mock_session, return_value, match):
    client = _make_local_client(mock_session)
    with patch.object(
        client, "_local_api_call", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = return_value
        with pytest.raises(TedeeClientException, match=match):
            await client.get_locks()


async def test_local_sync_updates_existing_lock(mock_session):
    client = _make_local_client(mock_session)
    client._locks[12345] = TedeeLock(
        name="Front Door", id=12345, type=2, state=TedeeLockState.LOCKED
    )
    with patch.object(
        client, "_local_api_call", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = (True, [{**LOCK_LOCAL_JSON, "state": 2}])
        await client.sync()
    assert client._locks[12345].state == TedeeLockState.UNLOCKED


async def test_local_sync_includes_settings(mock_session):
    """Local sync passes include_settings=True, updating deviceSettings."""
    client = _make_local_client(mock_session)
    client._locks[12345] = TedeeLock(
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
    with patch.object(
        client, "_local_api_call", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = (True, [updated])
        await client.sync()
    assert client._locks[12345].is_enabled_pullspring is False


async def test_local_sync_skips_unknown_lock_ids(mock_session):
    client = _make_local_client(mock_session)
    client._locks[1] = TedeeLock(name="L", id=1, type=2)
    with patch.object(
        client, "_local_api_call", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = (True, [{"id": 9999, "state": 2}])
        await client.sync()
    assert 9999 not in client._locks


@pytest.mark.parametrize(
    ("method", "expected_path", "expected_delay"),
    [
        ("lock", "/lock/1/lock", 5),
        ("unlock", "/lock/1/unlock?mode=3", 5),
        ("open", "/lock/1/unlock?mode=4", 5),  # duration_pullspring(4) + 1
        ("pull", "/lock/1/pull", 5),
    ],
    ids=["lock", "unlock", "open", "pull"],
)
async def test_local_lock_operation_paths_and_delays(
    mock_session, method, expected_path, expected_delay
):
    client = _make_local_client(mock_session)
    client._locks[1] = TedeeLock(
        name="L", id=1, type=2, duration_pullspring=4
    )
    with patch.object(
        client, "_local_api_call", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = (True, None)
        with patch(
            "aiotedee.client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            await getattr(client, method)(1)
    mock_call.assert_called_once_with(expected_path, HTTPMethod.POST)
    mock_sleep.assert_called_once_with(expected_delay)


async def test_local_lock_operation_failure_raises(mock_session):
    client = _make_local_client(mock_session)
    client._locks[1] = TedeeLock(name="L", id=1, type=2)
    with patch.object(
        client, "_local_api_call", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = (False, None)
        with pytest.raises(TedeeClientException):
            await client.lock(1)


async def test_local_get_bridge(mock_session):
    client = _make_local_client(mock_session)
    with patch.object(
        client, "_local_api_call", new_callable=AsyncMock
    ) as mock_call:
        mock_call.return_value = (True, BRIDGE_JSON)
        bridge = await client.get_local_bridge()
    assert bridge.id == 99
    assert bridge.serial == "12345678-0001"


async def test_local_get_bridge_not_configured_raises(mock_session):
    client = _make_local_client(mock_session, local_token="", local_ip="")
    with pytest.raises(TedeeClientException, match="Local API not configured"):
        await client.get_local_bridge()


@pytest.mark.parametrize(
    ("plain_mode", "token_value"),
    [(True, "tok"), (False, None)],
    ids=["plain", "hashed"],
)
def test_local_api_header_token_mode(mock_session, plain_mode, token_value):
    client = _make_local_client(mock_session, api_token_mode_plain=plain_mode)
    header = client._local_api_header
    if token_value:
        assert header["api_token"] == token_value
    else:
        # Hashed mode: sha256hex + timestamp digits → always > 64 chars
        assert len(header["api_token"]) > 64


def test_local_api_header_no_token_returns_empty(mock_session):
    client = _make_local_client(mock_session, local_token="")
    assert client._local_api_header == {}


# =============================================================================
# TedeeCloudClient
# =============================================================================


async def test_cloud_get_locks_success(mock_session):
    client = _make_cloud_client(mock_session)
    with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"result": [LOCK_CLOUD_JSON]}
        await client.get_locks()
    assert 12345 in client.locks_dict


async def test_cloud_get_locks_bridge_filter(mock_session):
    client = _make_cloud_client(mock_session, bridge_id=99)
    other_lock = {**LOCK_CLOUD_JSON, "id": 99999, "connectedToId": 50}
    with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"result": [LOCK_CLOUD_JSON, other_lock]}
        await client.get_locks()
    assert 12345 in client.locks_dict
    assert 99999 not in client.locks_dict


async def test_cloud_sync_does_not_include_settings(mock_session):
    """Cloud sync passes include_settings=False."""
    client = _make_cloud_client(mock_session)
    client._locks[12345] = TedeeLock(
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
    with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"result": [sync_response]}
        await client.sync()
    assert client._locks[12345].state == TedeeLockState.UNLOCKED
    # Settings NOT updated (cloud sync)
    assert client._locks[12345].is_enabled_pullspring is True
    assert client._locks[12345].duration_pullspring == 7


async def test_cloud_get_bridges(mock_session):
    client = _make_cloud_client(mock_session)
    with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"result": [BRIDGE_JSON]}
        bridges = await client.get_bridges()
    assert len(bridges) == 1
    assert bridges[0].id == 99


async def test_cloud_lock_sends_correct_url(mock_session):
    client = _make_cloud_client(mock_session)
    client._locks[1] = TedeeLock(name="L", id=1, type=2)
    with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
        with patch("aiotedee.client.asyncio.sleep", new_callable=AsyncMock):
            await client.lock(1)
    assert "/1/operation/lock" in mock_req.call_args[0][0]
