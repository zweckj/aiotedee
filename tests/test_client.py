"""Tests for the client hierarchy: base, local, cloud, combined."""

from __future__ import annotations

from http import HTTPMethod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession

from aiotedee import (
    TedeeClient,
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


def _make_combined_client(mock_session, **overrides):
    defaults = dict(
        personal_token="cloud-key",
        local_token="tok",
        local_ip="192.168.1.1",
        session=mock_session,
    )
    defaults.update(overrides)
    return TedeeClient(**defaults)


# =============================================================================
# Base / shared behaviour (tested via TedeeLocalClient for simplicity)
# =============================================================================


class TestBridgeFiltering:
    """_filter_by_bridge correctly narrows results."""

    def test_no_bridge_id_returns_all(self, mock_session):
        client = _make_local_client(mock_session)
        locks = [{"connectedToId": 1}, {"connectedToId": 2}]
        assert client._filter_by_bridge(locks) == locks

    def test_filters_to_matching_bridge(self, mock_session):
        client = _make_local_client(mock_session, bridge_id=1)
        locks = [{"connectedToId": 1}, {"connectedToId": 2}]
        assert client._filter_by_bridge(locks) == [{"connectedToId": 1}]

    def test_includes_locks_without_bridge(self, mock_session):
        """Locks with connectedToId=None pass through all filters."""
        client = _make_local_client(mock_session, bridge_id=1)
        locks = [{"connectedToId": None}, {"connectedToId": 2}]
        assert client._filter_by_bridge(locks) == [{"connectedToId": None}]


class TestWebhookParsing:
    """parse_webhook_message dispatches to correct handlers."""

    def test_lock_status_changed(self, mock_session):
        client = _make_local_client(mock_session)
        lock = TedeeLock(name="L", id=1, type=2, state=TedeeLockState.LOCKED)
        client._locks[1] = lock

        client.parse_webhook_message({
            "event": "lock-status-changed",
            "data": {"deviceId": 1, "state": 2, "jammed": 0, "doorState": 3},
        })

        assert client._locks[1].state == TedeeLockState.UNLOCKED

    def test_missing_data_raises(self, mock_session):
        client = _make_local_client(mock_session)
        with pytest.raises(TedeeWebhookException):
            client.parse_webhook_message({"event": "lock-status-changed"})

    def test_backend_connection_changed_ignored(self, mock_session):
        """backend-connection-changed is silently skipped."""
        client = _make_local_client(mock_session)
        client.parse_webhook_message({
            "event": "backend-connection-changed",
            "data": {},
        })

    def test_unknown_device_ignored(self, mock_session):
        """Messages for unknown lock IDs are silently skipped."""
        client = _make_local_client(mock_session)
        client.parse_webhook_message({
            "event": "lock-status-changed",
            "data": {"deviceId": 999, "state": 2, "jammed": 0, "doorState": 3},
        })
        assert 999 not in client._locks

    def test_unknown_event_ignored(self, mock_session):
        """Unrecognised events are silently skipped."""
        client = _make_local_client(mock_session)
        client._locks[1] = TedeeLock(name="L", id=1, type=2)
        # Should not raise
        client.parse_webhook_message({
            "event": "some-future-event",
            "data": {"deviceId": 1},
        })


class TestIsLockedUnlocked:
    def test_is_locked(self, mock_session):
        client = _make_local_client(mock_session)
        client._locks[1] = TedeeLock(
            name="L", id=1, type=2, state=TedeeLockState.LOCKED
        )
        assert client.is_locked(1) is True
        assert client.is_unlocked(1) is False

    def test_is_unlocked(self, mock_session):
        client = _make_local_client(mock_session)
        client._locks[1] = TedeeLock(
            name="L", id=1, type=2, state=TedeeLockState.UNLOCKED
        )
        assert client.is_locked(1) is False
        assert client.is_unlocked(1) is True


# =============================================================================
# TedeeLocalClient
# =============================================================================


class TestLocalClientGetLocks:
    async def test_get_locks_success(self, mock_session):
        client = _make_local_client(mock_session)
        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (True, [LOCK_LOCAL_JSON])
            await client.get_locks()

        assert 12345 in client.locks_dict
        assert client.locks_dict[12345].name == "Front Door"

    async def test_get_locks_failure_raises(self, mock_session):
        client = _make_local_client(mock_session)
        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (False, None)
            with pytest.raises(TedeeClientException):
                await client.get_locks()

    async def test_get_locks_empty_result_raises(self, mock_session):
        client = _make_local_client(mock_session)
        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (True, [])
            with pytest.raises(TedeeClientException, match="No lock found"):
                await client.get_locks()


class TestLocalClientSync:
    async def test_sync_updates_existing_lock(self, mock_session):
        client = _make_local_client(mock_session)
        client._locks[12345] = TedeeLock(
            name="Front Door", id=12345, type=2, state=TedeeLockState.LOCKED
        )

        updated = {**LOCK_LOCAL_JSON, "state": 2}  # UNLOCKED
        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (True, [updated])
            await client.sync()

        assert client._locks[12345].state == TedeeLockState.UNLOCKED

    async def test_sync_includes_settings_for_local(self, mock_session):
        """Local sync passes include_settings=True."""
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
        assert client._locks[12345].is_enabled_auto_pullspring is True
        assert client._locks[12345].duration_pullspring == 3

    async def test_sync_skips_unknown_lock_ids(self, mock_session):
        client = _make_local_client(mock_session)
        client._locks[1] = TedeeLock(name="L", id=1, type=2)

        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (True, [{"id": 9999, "state": 2}])
            await client.sync()

        assert 9999 not in client._locks


class TestLocalClientLockOperations:
    async def test_lock_calls_correct_path(self, mock_session):
        client = _make_local_client(mock_session)
        client._locks[1] = TedeeLock(name="L", id=1, type=2)

        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (True, None)
            with patch("aiotedee.client.asyncio.sleep", new_callable=AsyncMock):
                await client.lock(1)

        mock_call.assert_called_once_with("/lock/1/lock", HTTPMethod.POST)

    async def test_unlock_calls_correct_path(self, mock_session):
        client = _make_local_client(mock_session)
        client._locks[1] = TedeeLock(name="L", id=1, type=2)

        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (True, None)
            with patch("aiotedee.client.asyncio.sleep", new_callable=AsyncMock):
                await client.unlock(1)

        mock_call.assert_called_once_with(
            "/lock/1/unlock?mode=3", HTTPMethod.POST
        )

    async def test_open_uses_pullspring_delay(self, mock_session):
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
                await client.open(1)

        mock_sleep.assert_called_once_with(5)  # duration + 1

    async def test_local_operation_failure_raises(self, mock_session):
        client = _make_local_client(mock_session)
        client._locks[1] = TedeeLock(name="L", id=1, type=2)

        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (False, None)
            with pytest.raises(TedeeClientException):
                await client.lock(1)


class TestLocalClientBridge:
    async def test_get_local_bridge(self, mock_session):
        client = _make_local_client(mock_session)
        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = (True, BRIDGE_JSON)
            bridge = await client.get_local_bridge()

        assert bridge.id == 99
        assert bridge.serial == "12345678-0001"

    async def test_get_local_bridge_not_configured(self, mock_session):
        client = _make_local_client(mock_session, local_token="", local_ip="")
        with pytest.raises(TedeeClientException, match="Local API not configured"):
            await client.get_local_bridge()


class TestLocalApiHeader:
    def test_plain_mode(self, mock_session):
        client = _make_local_client(mock_session, api_token_mode_plain=True)
        header = client._local_api_header
        assert header["api_token"] == "tok"

    def test_hashed_mode(self, mock_session):
        client = _make_local_client(mock_session, api_token_mode_plain=False)
        header = client._local_api_header
        # Should be sha256hex + timestamp digits
        assert len(header["api_token"]) > 64
        assert "api_token" in header

    def test_no_token_returns_empty(self, mock_session):
        client = _make_local_client(mock_session, local_token="")
        assert client._local_api_header == {}


# =============================================================================
# TedeeCloudClient
# =============================================================================


class TestCloudClientGetLocks:
    async def test_get_locks_success(self, mock_session):
        client = _make_cloud_client(mock_session)
        with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"result": [LOCK_CLOUD_JSON]}
            await client.get_locks()

        assert 12345 in client.locks_dict

    async def test_get_locks_with_bridge_filter(self, mock_session):
        client = _make_cloud_client(mock_session, bridge_id=99)
        other_lock = {**LOCK_CLOUD_JSON, "id": 99999, "connectedToId": 50}

        with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"result": [LOCK_CLOUD_JSON, other_lock]}
            await client.get_locks()

        assert 12345 in client.locks_dict
        assert 99999 not in client.locks_dict


class TestCloudClientSync:
    async def test_sync_does_not_include_settings(self, mock_session):
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

        # State updated
        assert client._locks[12345].state == TedeeLockState.UNLOCKED
        # Settings NOT updated (cloud sync)
        assert client._locks[12345].is_enabled_pullspring is True
        assert client._locks[12345].duration_pullspring == 7


class TestCloudClientGetBridges:
    async def test_get_bridges(self, mock_session):
        client = _make_cloud_client(mock_session)
        with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"result": [BRIDGE_JSON]}
            bridges = await client.get_bridges()

        assert len(bridges) == 1
        assert bridges[0].id == 99


class TestCloudClientLockOperation:
    async def test_lock_sends_correct_url(self, mock_session):
        client = _make_cloud_client(mock_session)
        client._locks[1] = TedeeLock(name="L", id=1, type=2)

        with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
            with patch("aiotedee.client.asyncio.sleep", new_callable=AsyncMock):
                await client.lock(1)

        call_args = mock_req.call_args
        assert "/1/operation/lock" in call_args[0][0]


# =============================================================================
# TedeeClient (combined)
# =============================================================================


class TestCombinedClientFallback:
    async def test_fetch_locks_local_first(self, mock_session):
        """When local succeeds, cloud is not called."""
        client = _make_combined_client(mock_session)

        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_local:
            mock_local.return_value = (True, [LOCK_LOCAL_JSON])
            with patch(
                "aiotedee.client.http_request", new_callable=AsyncMock
            ) as mock_cloud:
                await client.get_locks()

        mock_cloud.assert_not_called()
        assert 12345 in client.locks_dict

    async def test_fetch_locks_falls_back_to_cloud(self, mock_session):
        """When local fails, falls back to cloud."""
        client = _make_combined_client(mock_session)

        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_local:
            mock_local.return_value = (False, None)
            with patch(
                "aiotedee.client.http_request", new_callable=AsyncMock
            ) as mock_cloud:
                mock_cloud.return_value = {"result": [LOCK_CLOUD_JSON]}
                await client.get_locks()

        assert 12345 in client.locks_dict

    async def test_sync_local_sets_include_settings_true(self, mock_session):
        """Local sync passes include_settings=True for device settings."""
        client = _make_combined_client(mock_session)
        client._locks[12345] = TedeeLock(
            name="Front Door",
            id=12345,
            type=2,
            is_enabled_pullspring=True,
            duration_pullspring=7,
        )

        updated = {
            **LOCK_LOCAL_JSON,
            "deviceSettings": {
                "pullSpringEnabled": False,
                "autoPullSpringEnabled": True,
                "pullSpringDuration": 2,
            },
        }
        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_local:
            mock_local.return_value = (True, [updated])
            await client.sync()

        assert client._locks[12345].is_enabled_pullspring is False
        assert client._locks[12345].duration_pullspring == 2

    async def test_sync_cloud_fallback_no_settings(self, mock_session):
        """Cloud sync fallback does NOT update settings."""
        client = _make_combined_client(mock_session)
        client._locks[12345] = TedeeLock(
            name="Front Door",
            id=12345,
            type=2,
            is_enabled_pullspring=True,
            duration_pullspring=7,
        )

        sync_data = {
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
        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_local:
            mock_local.return_value = (False, None)
            with patch(
                "aiotedee.client.http_request", new_callable=AsyncMock
            ) as mock_cloud:
                mock_cloud.return_value = {"result": [sync_data]}
                await client.sync()

        assert client._locks[12345].is_enabled_pullspring is True
        assert client._locks[12345].duration_pullspring == 7

    async def test_lock_operation_local_first(self, mock_session):
        client = _make_combined_client(mock_session)
        client._locks[1] = TedeeLock(name="L", id=1, type=2)

        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_local:
            mock_local.return_value = (True, None)
            with patch(
                "aiotedee.client.http_request", new_callable=AsyncMock
            ) as mock_cloud:
                with patch(
                    "aiotedee.client.asyncio.sleep", new_callable=AsyncMock
                ):
                    await client.lock(1)

        mock_local.assert_called_once()
        mock_cloud.assert_not_called()

    async def test_lock_operation_cloud_fallback(self, mock_session):
        client = _make_combined_client(mock_session)
        client._locks[1] = TedeeLock(name="L", id=1, type=2)

        with patch.object(
            client, "_local_api_call", new_callable=AsyncMock
        ) as mock_local:
            mock_local.return_value = (False, None)
            with patch(
                "aiotedee.client.http_request", new_callable=AsyncMock
            ) as mock_cloud:
                with patch(
                    "aiotedee.client.asyncio.sleep", new_callable=AsyncMock
                ):
                    await client.lock(1)

        mock_cloud.assert_called_once()

    async def test_cloud_only_mode(self, mock_session):
        """Client with no local credentials uses cloud directly."""
        client = TedeeClient(personal_token="key", session=mock_session)
        assert client._use_local_api is False

        with patch("aiotedee.client.http_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"result": [LOCK_CLOUD_JSON]}
            await client.get_locks()

        assert 12345 in client.locks_dict
