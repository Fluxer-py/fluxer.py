from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _maybe_int(value: Any) -> int | None:
    return int(value) if value is not None else None


class RawMessageDeleteEvent:
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.message_id = _maybe_int(data.get("id"))
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.raw_data = data


class RawBulkMessageDeleteEvent:
    def __init__(self, data: Mapping[str, Any]) -> None:
        raw_ids = data.get("ids", data.get("message_ids", []))
        ids = raw_ids if isinstance(raw_ids, Iterable) else []
        self.message_ids = [int(value) for value in ids]
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.raw_data = data


class RawMessageUpdateEvent:
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.message_id = _maybe_int(data.get("id"))
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.data = data
