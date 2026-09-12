"""Custom-status input and legacy rich-activity compatibility containers.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BaseActivity:
    """Legacy activity metadata for compatibility with existing callers.

    Only custom-status input can be published through Fluxer presence.

    Attributes:
        name: Name to assign or resolve in this operation.
        type: Type used by this operation.
    """

    name: str | None = None
    type: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize this object's supported fields to a dictionary.

        Returns:
            The serialized representation with supported fields preserved.
        """
        payload: dict[str, Any] = {"name": self.name, "type": self.type}
        for key, value in self._extra_payload().items():
            if value is not None:
                payload[key] = value
        return payload

    def _extra_payload(self) -> dict[str, Any]:
        return {}


class Activity(BaseActivity):
    """Compatibility activity metadata; rich activity publishing is unsupported.

    Attributes:
        name: Name to assign or resolve in this operation.
        type: Type used by this operation.
    """

    pass


class Game(BaseActivity):
    """Compatibility game activity metadata; Gateway presence rejects this rich activity.

    Attributes:
        name: Name to assign or resolve in this operation.
        type: Type used by this operation.
    """

    def __init__(self, name: str) -> None:
        """Initialize the game with the supplied configuration.

        Args:
            name: Name to assign or resolve in this operation.
        """
        super().__init__(name=name, type=0)


class Streaming(BaseActivity):
    """Compatibility streaming metadata; Gateway presence rejects this rich activity.

    Attributes:
        name: Name to assign or resolve in this operation.
        type: Type used by this operation.
        url: Absolute destination or resource URL.
    """

    def __init__(self, *, name: str, url: str) -> None:
        """Initialize the streaming with the supplied configuration.

        Args:
            name: Name to assign or resolve in this operation.
            url: Absolute destination or resource URL.
        """
        super().__init__(name=name, type=1)
        self.url: str = url

    def _extra_payload(self) -> dict[str, Any]:
        return {"url": self.url}


class CustomActivity(BaseActivity):
    """Custom-status text accepted by the Fluxer presence helpers.

    Attributes:
        name: Name to assign or resolve in this operation.
        type: Type used by this operation.
    """

    pass


class Spotify(BaseActivity):
    """Compatibility Spotify metadata; Gateway presence rejects this rich activity.

    Attributes:
        name: Name to assign or resolve in this operation.
        type: Type used by this operation.
    """

    pass


def create_activity(data: dict[str, Any] | None) -> BaseActivity | None:
    """Parse legacy activity metadata into a compatibility container.

    Args:
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

    Returns:
        The result of this operation.
    """
    if data is None:
        return None
    return Activity(name=data.get("name"), type=data.get("type", 0))


__all__ = (
    "BaseActivity",
    "Activity",
    "Game",
    "Streaming",
    "CustomActivity",
    "Spotify",
    "create_activity",
)
