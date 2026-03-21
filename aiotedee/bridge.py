"""Tedee Bridge model."""

from __future__ import annotations

from dataclasses import dataclass

from mashumaro.mixins.dict import DataClassDictMixin


@dataclass
class TedeeBridge(DataClassDictMixin):
    """Tedee Bridge."""

    id: int
    serial: str
    name: str

    @classmethod
    def from_api_response(cls, data: dict) -> TedeeBridge:
        """Create a TedeeBridge from an API response dict."""
        return cls(
            id=data.get("id", 0),
            serial=data["serialNumber"],
            name=data["name"],
        )
