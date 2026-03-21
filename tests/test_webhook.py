"""Tests for webhook event handlers."""

from __future__ import annotations

import pytest

from aiotedee import TedeeDoorState, TedeeLockState
from aiotedee.webhook import WEBHOOK_HANDLERS


EXPECTED_EVENTS = {
    "device-connection-changed",
    "lock-status-changed",
    "device-battery-level-changed",
    "device-battery-start-charging",
    "device-battery-stop-charging",
    "device-battery-fully-charged",
    "device-settings-changed",
}


def test_all_expected_events_registered():
    assert set(WEBHOOK_HANDLERS.keys()) == EXPECTED_EVENTS


def test_connection_changed(sample_lock):
    WEBHOOK_HANDLERS["device-connection-changed"](sample_lock, {"isConnected": 0})
    assert sample_lock.is_connected is False
    WEBHOOK_HANDLERS["device-connection-changed"](sample_lock, {"isConnected": 1})
    assert sample_lock.is_connected is True


def test_lock_status_changed(sample_lock):
    WEBHOOK_HANDLERS["lock-status-changed"](
        sample_lock, {"state": 2, "jammed": 1, "doorState": 2}
    )
    assert sample_lock.state == TedeeLockState.UNLOCKED
    assert sample_lock.is_jammed is True
    assert sample_lock.door_state == TedeeDoorState.OPENED


def test_lock_status_unknown_values_fallback(sample_lock):
    """Unknown state/door integers fall back gracefully."""
    WEBHOOK_HANDLERS["lock-status-changed"](
        sample_lock, {"state": 999, "jammed": 0, "doorState": 999}
    )
    assert sample_lock.state == TedeeLockState.UNKNOWN
    assert sample_lock.door_state == TedeeDoorState.NOT_PAIRED


def test_battery_level_changed(sample_lock):
    WEBHOOK_HANDLERS["device-battery-level-changed"](
        sample_lock, {"batteryLevel": 42}
    )
    assert sample_lock.battery_level == 42


@pytest.mark.parametrize(
    ("event", "initial_charging", "expected_charging", "expected_battery"),
    [
        ("device-battery-start-charging", False, True, 80),
        ("device-battery-stop-charging", True, False, 80),
        ("device-battery-fully-charged", True, False, 100),
    ],
    ids=["start-charging", "stop-charging", "fully-charged"],
)
def test_battery_charging_events(
    sample_lock, event, initial_charging, expected_charging, expected_battery
):
    sample_lock.is_charging = initial_charging
    WEBHOOK_HANDLERS[event](sample_lock, {})
    assert sample_lock.is_charging is expected_charging
    assert sample_lock.battery_level == expected_battery


def test_settings_changed_noop(sample_lock):
    """device-settings-changed is a registered no-op."""
    original_state = sample_lock.state
    WEBHOOK_HANDLERS["device-settings-changed"](sample_lock, {})
    assert sample_lock.state == original_state
