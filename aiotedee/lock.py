"""Tedee Lock models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from mashumaro.mixins.dict import DataClassDictMixin


class TedeeLockState(IntEnum):
    """Tedee Lock State."""

    UNCALIBRATED = 0
    CALIBRATING = 1
    UNLOCKED = 2
    HALF_OPEN = 3
    UNLOCKING = 4
    LOCKING = 5
    LOCKED = 6
    PULLED = 7
    PULLING = 8
    UNKNOWN = 9
    UPDATING = 18
    UNPULLING = 255


class TedeeDoorState(IntEnum):
    """Tedee Door State."""

    NOT_PAIRED = 0
    DISCONNECTED = 1
    OPENED = 2
    CLOSED = 3
    UNCALIBRATED = 4


_LOCK_TYPE_NAMES: dict[int, str] = {
    2: "Tedee PRO",
    4: "Tedee GO",
}

DEFAULT_PULLSPRING_DURATION = 5


@dataclass
class TedeeLock(DataClassDictMixin):
    """Tedee Lock."""

    name: str
    id: int
    type: int
    state: TedeeLockState = TedeeLockState.UNCALIBRATED
    battery_level: int | None = None
    is_connected: bool = False
    is_charging: bool = False
    state_change_result: int = 0
    is_enabled_pullspring: bool = False
    is_enabled_auto_pullspring: bool = False
    duration_pullspring: int = DEFAULT_PULLSPRING_DURATION
    door_state: TedeeDoorState = TedeeDoorState.NOT_PAIRED

    @property
    def type_name(self) -> str:
        """Return the human-readable type of the lock."""
        return _LOCK_TYPE_NAMES.get(self.type, "Unknown Model")

    @property
    def is_locked(self) -> bool:
        """Return true if the lock is locked."""
        return self.state == TedeeLockState.LOCKED

    @property
    def is_unlocked(self) -> bool:
        """Return true if the lock is unlocked."""
        return self.state == TedeeLockState.UNLOCKED

    @property
    def is_jammed(self) -> bool:
        """Return true if the lock is jammed."""
        return self.state_change_result == 1

    @classmethod
    def from_api_response(cls, data: dict) -> TedeeLock:
        """Create a TedeeLock from an API response dict (cloud or local)."""
        state, battery, charging, change_result, door = _parse_lock_properties(data)
        pullspring, auto_pull, duration = _parse_pull_spring_settings(data)

        return cls(
            name=data["name"],
            id=data["id"],
            type=data.get("type", 0),
            state=state,
            battery_level=battery,
            is_connected=bool(data.get("isConnected", False)),
            is_charging=charging,
            state_change_result=change_result,
            is_enabled_pullspring=pullspring,
            is_enabled_auto_pullspring=auto_pull,
            duration_pullspring=duration,
            door_state=door,
        )

    def update_from_api_response(
        self, data: dict, *, include_settings: bool = False
    ) -> None:
        """Update this lock in-place from an API response dict."""
        state, battery, charging, change_result, door = _parse_lock_properties(data)

        self.is_connected = bool(data.get("isConnected", False))
        self.state = state
        self.battery_level = battery
        self.is_charging = charging
        self.state_change_result = change_result
        self.door_state = door

        if include_settings:
            (
                self.is_enabled_pullspring,
                self.is_enabled_auto_pullspring,
                self.duration_pullspring,
            ) = _parse_pull_spring_settings(data)


def _parse_lock_properties(
    data: dict,
) -> tuple[TedeeLockState, int | None, bool, int, TedeeDoorState]:
    """Extract lock state properties from an API response.

    The cloud API nests values under ``lockProperties`` while the local API
    places them at the top level.
    """
    lock_props = data.get("lockProperties")
    source = lock_props if lock_props is not None else data

    state = TedeeLockState(source.get("state", TedeeLockState.UNKNOWN))
    battery_level: int | None = source.get("batteryLevel")
    is_charging = bool(source.get("isCharging", False))
    door_state = TedeeDoorState(source.get("doorState", TedeeDoorState.NOT_PAIRED))

    # The cloud API uses ``stateChangeResult`` while the local API uses ``jammed``.
    if lock_props is not None:
        state_change_result: int = source.get("stateChangeResult", 0)
    else:
        state_change_result = source.get("jammed", 0)

    return state, battery_level, is_charging, state_change_result, door_state


def _parse_pull_spring_settings(data: dict) -> tuple[bool, bool, int]:
    """Extract pull-spring settings from an API response."""
    device_settings: dict = data.get("deviceSettings", {})
    return (
        bool(device_settings.get("pullSpringEnabled", False)),
        bool(device_settings.get("autoPullSpringEnabled", False)),
        device_settings.get("pullSpringDuration", DEFAULT_PULLSPRING_DURATION),
    )
