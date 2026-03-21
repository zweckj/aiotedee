"""Tests for webhook event handlers."""

from __future__ import annotations

from aiotedee import TedeeDoorState, TedeeLock, TedeeLockState, TedeeWebhookException
from aiotedee.webhook import WEBHOOK_HANDLERS


class TestWebhookHandlers:
    """Individual webhook handler functions."""

    def test_connection_changed_connected(self, sample_lock):
        WEBHOOK_HANDLERS["device-connection-changed"](
            sample_lock, {"isConnected": 1}
        )
        assert sample_lock.is_connected is True

    def test_connection_changed_disconnected(self, sample_lock):
        WEBHOOK_HANDLERS["device-connection-changed"](
            sample_lock, {"isConnected": 0}
        )
        assert sample_lock.is_connected is False

    def test_lock_status_changed(self, sample_lock):
        WEBHOOK_HANDLERS["lock-status-changed"](
            sample_lock,
            {"state": 2, "jammed": 1, "doorState": 2},
        )
        assert sample_lock.state == TedeeLockState.UNLOCKED
        assert sample_lock.is_jammed is True
        assert sample_lock.door_state == TedeeDoorState.OPENED

    def test_lock_status_unknown_state_value(self, sample_lock):
        """Unknown state integer falls back gracefully."""
        WEBHOOK_HANDLERS["lock-status-changed"](
            sample_lock,
            {"state": 999, "jammed": 0, "doorState": 999},
        )
        assert sample_lock.state == TedeeLockState.UNKNOWN
        assert sample_lock.door_state == TedeeDoorState.NOT_PAIRED

    def test_battery_level_changed(self, sample_lock):
        WEBHOOK_HANDLERS["device-battery-level-changed"](
            sample_lock, {"batteryLevel": 42}
        )
        assert sample_lock.battery_level == 42

    def test_battery_start_charging(self, sample_lock):
        sample_lock.is_charging = False
        WEBHOOK_HANDLERS["device-battery-start-charging"](sample_lock, {})
        assert sample_lock.is_charging is True

    def test_battery_stop_charging(self, sample_lock):
        sample_lock.is_charging = True
        WEBHOOK_HANDLERS["device-battery-stop-charging"](sample_lock, {})
        assert sample_lock.is_charging is False

    def test_battery_fully_charged(self, sample_lock):
        sample_lock.is_charging = True
        sample_lock.battery_level = 95
        WEBHOOK_HANDLERS["device-battery-fully-charged"](sample_lock, {})
        assert sample_lock.is_charging is False
        assert sample_lock.battery_level == 100

    def test_settings_changed_noop(self, sample_lock):
        """device-settings-changed is a registered no-op."""
        original_state = sample_lock.state
        WEBHOOK_HANDLERS["device-settings-changed"](sample_lock, {})
        assert sample_lock.state == original_state


class TestWebhookDispatchTable:
    """The WEBHOOK_HANDLERS dispatch table is complete and correct."""

    EXPECTED_EVENTS = {
        "device-connection-changed",
        "lock-status-changed",
        "device-battery-level-changed",
        "device-battery-start-charging",
        "device-battery-stop-charging",
        "device-battery-fully-charged",
        "device-settings-changed",
    }

    def test_all_expected_events_registered(self):
        assert set(WEBHOOK_HANDLERS.keys()) == self.EXPECTED_EVENTS

    def test_unknown_event_not_in_table(self):
        assert WEBHOOK_HANDLERS.get("unknown-event") is None
