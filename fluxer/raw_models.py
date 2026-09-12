"""Raw models helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _maybe_int(value: Any) -> int | None:
    return int(value) if value is not None else None


class RawMessageDeleteEvent:
    """Raw Message Delete Event data and behaviour.

    Attributes:
        message_id: Message identity supplied by the event or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    message_id: int | None
    channel_id: int | None
    guild_id: int | None

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Initialize the raw message delete event with the supplied configuration.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
        """
        self.message_id = _maybe_int(data.get("id"))
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.raw_data: Mapping[str, Any] = data


class RawBulkMessageDeleteEvent:
    """Raw Bulk Message Delete Event data and behaviour.

    Attributes:
        message_ids: Identities of the messages named by the bulk event.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    message_ids: list[int]
    channel_id: int | None
    guild_id: int | None

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Initialize the raw bulk message delete event with the supplied configuration.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
        """
        raw_ids = data.get("ids", data.get("message_ids", []))
        ids = raw_ids if isinstance(raw_ids, Iterable) else []
        self.message_ids = [int(value) for value in ids]
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.raw_data: Mapping[str, Any] = data


class RawMessageUpdateEvent:
    """Raw Message Update Event data and behaviour.

    Attributes:
        message_id: Message identity supplied by the event or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    message_id: int | None
    channel_id: int | None
    guild_id: int | None

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Initialize the raw message update event with the supplied configuration.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
        """
        self.message_id = _maybe_int(data.get("id"))
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.data: Mapping[str, Any] = data


__all__ = (
    "RawMessageDeleteEvent",
    "RawBulkMessageDeleteEvent",
    "RawMessageUpdateEvent",
)
