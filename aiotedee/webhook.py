"""Webhook event handlers for aiotedee."""

from __future__ import annotations

from typing import Any, Callable

from .models import (
    TedeeDoorState,
    TedeeLock,
    TedeeLockState,
    _safe_door_state,
    _safe_lock_state,
)


def _handle_connection_changed(lock: TedeeLock, data: dict) -> None:
    lock.is_connected = data.get("isConnected", 0) == 1


def _handle_lock_status_changed(lock: TedeeLock, data: dict) -> None:
    lock.state = _safe_lock_state(data.get("state", 0))
    lock.state_change_result = data.get("jammed", 0)
    lock.door_state = _safe_door_state(data.get("doorState", 0))


def _handle_battery_level_changed(lock: TedeeLock, data: dict) -> None:
    lock.battery_level = data.get("batteryLevel")


def _handle_battery_start_charging(lock: TedeeLock, _data: dict) -> None:
    lock.is_charging = True


def _handle_battery_stop_charging(lock: TedeeLock, _data: dict) -> None:
    lock.is_charging = False


def _handle_battery_fully_charged(lock: TedeeLock, _data: dict) -> None:
    lock.is_charging = False
    lock.battery_level = 100


def _noop(_lock: TedeeLock, _data: dict) -> None:
    pass


WebhookHandler = Callable[[TedeeLock, dict[str, Any]], None]

WEBHOOK_HANDLERS: dict[str, WebhookHandler] = {
    "device-connection-changed": _handle_connection_changed,
    "lock-status-changed": _handle_lock_status_changed,
    "device-battery-level-changed": _handle_battery_level_changed,
    "device-battery-start-charging": _handle_battery_start_charging,
    "device-battery-stop-charging": _handle_battery_stop_charging,
    "device-battery-fully-charged": _handle_battery_fully_charged,
    "device-settings-changed": _noop,
}
