""" Class describing a tedee bridge. """


class TedeeBridge:
    """Dataclass for tedee bridge."""

    def __init__(self, bridge_id: int, serial: str, name: str):
        self._bridge_id = bridge_id
        self._serial = serial
        self._name = name

    @property
    def bridge_id(self) -> int:
        """Return bridge id."""
        return self._bridge_id

    @property
    def serial(self) -> str:
        """Return bridge serial."""
        return self._serial

    @property
    def name(self) -> str:
        """Return bridge name."""
        return self._name
