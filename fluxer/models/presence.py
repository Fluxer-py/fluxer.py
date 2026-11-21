"""Presence sub-objects carried by Fluxer Presence Update dispatches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..utils import _try_parse_time as parse_time


@dataclass(slots=True)
class CustomStatus:
    """A user's custom status.

    Attributes:
        text: Custom status text.
        expires_at: When the custom status expires.
        emoji_id: Custom emoji ID.
        emoji_name: Unicode emoji, or the custom emoji's name.
        emoji_animated: Whether the custom emoji is animated.
    """

    text: str | None = None
    expires_at: datetime | None = None
    emoji_id: int | None = None
    emoji_name: str | None = None
    emoji_animated: bool = False

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> CustomStatus:
        """Build a custom status from its decoded payload.

        Args:
            data: Custom status object.

        Returns:
            The parsed custom status.
        """
        emoji_id = data.get("emoji_id")
        return cls(
            text=data.get("text"),
            expires_at=parse_time(data.get("expires_at")),
            emoji_id=int(emoji_id) if emoji_id is not None else None,
            emoji_name=data.get("emoji_name"),
            emoji_animated=bool(data.get("emoji_animated", False)),
        )


__all__ = ("CustomStatus",)
