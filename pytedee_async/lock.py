"""Tedee Lock Object."""

from enum import IntEnum


class TedeeLockState(IntEnum):
    """Tedee Lock State."""

    UNKNOWN = 0
    UNLOCKED = 2
    HALF_OPEN = 3
    UNLOCKING = 4
    LOCKING = 5
    LOCKED = 6
    PULLED = 7


class TedeeLock:
    """Tedee Lock."""

    def __init__(
        self,
        lock_name: str,
        lock_id: int,
        lock_type: int,
        state: int = 0,
        battery_level: int | None = None,
        is_connected: bool = False,
        is_charging: bool = False,
        state_change_result: int = 0,
        is_enabled_pullspring: bool = False,
        duration_pullspring: int = 0,
    ) -> None:
        """Initialize a new lock."""
        self._lock_name = lock_name
        self._lock_id = lock_id
        self._lock_type = lock_type
        self._state = state
        self._battery_level = battery_level
        self._is_connected = is_connected
        self._is_charging = is_charging
        self._state_change_result = state_change_result
        self._duration_pullspring = duration_pullspring
        self._is_enabled_pullspring = is_enabled_pullspring

    @property
    def lock_name(self) -> str:
        """Return the name of the lock."""
        return self._lock_name

    @property
    def lock_id(self) -> int:
        """Return the id of the lock."""
        return self._lock_id

    @property
    def lock_type(self) -> str:
        """Return the type of the lock."""
        if self._lock_type == 2:
            return "Tedee PRO"
        elif self._lock_type == 4:
            return "Tedee GO"
        else:
            return "Unknown Model"

    @property
    def is_state_locked(self) -> bool:
        """Return true if the lock is locked."""
        return self._state == TedeeLockState.LOCKED

    @property
    def is_state_unlocked(self) -> bool:
        """Return true if the lock is unlocked."""
        return self._state == TedeeLockState.UNLOCKED

    @property
    def is_state_jammed(self) -> bool:
        """Return true if the lock is jammed."""
        return self._state_change_result == 1

    @property
    def state(self) -> TedeeLockState:
        """Return the state of the lock."""
        return TedeeLockState(self._state)

    @state.setter
    def state(self, status: int):
        self._state = status

    @property
    def state_change_result(self) -> int:
        """Return the state change result of the lock."""
        return self._state_change_result

    @state_change_result.setter
    def state_change_result(self, result: int):
        self._state_change_result = result

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the lock."""
        return self._battery_level

    @battery_level.setter
    def battery_level(self, level):
        self._battery_level = level

    @property
    def is_connected(self) -> bool:
        """Return true if the lock is connected."""
        return self._is_connected

    @is_connected.setter
    def is_connected(self, connected):
        self._is_connected = connected

    @property
    def is_charging(self) -> bool:
        """Return true if the lock is charging."""
        return self._is_charging

    @is_charging.setter
    def is_charging(self, value: bool):
        self._is_charging = value

    @property
    def is_enabled_pullspring(self) -> bool:
        """Return true if the lock is charging."""
        return bool(self._is_enabled_pullspring)

    @is_enabled_pullspring.setter
    def is_enabled_pullspring(self, value: bool):
        self._is_enabled_pullspring = value

    @property
    def duration_pullspring(self) -> int:
        """Return the duration of the pullspring."""
        return self._duration_pullspring

    @duration_pullspring.setter
    def duration_pullspring(self, duration: int):
        self._duration_pullspring = duration

    def to_dict(self) -> dict[str, str | int | bool | None]:
        """Return a dict representation of the lock."""
        return {
            "lock_name": self._lock_name,
            "lock_id": self._lock_id,
            "lock_type": self._lock_type,
            "state": self._state,
            "battery_level": self._battery_level,
            "is_connected": self._is_connected,
            "is_charging": self._is_charging,
            "state_change_result": self._state_change_result,
            "is_enabled_pullspring": self._is_enabled_pullspring,
            "duration_pullspring": self._duration_pullspring,
        }
