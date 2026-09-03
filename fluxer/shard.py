from __future__ import annotations

from dataclasses import dataclass

from .client import Client


@dataclass(slots=True)
class ShardInfo:
    id: int
    shard_count: int


class AutoShardedClient(Client):
    pass


class Shard:
    pass


class EventType:
    pass


class EventItem:
    pass
