"""Shard metadata and compatibility classes without automatic sharding orchestration.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import Client


@dataclass(slots=True)
class ShardInfo:
    """Shard Info data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
        shard_count: Shard count used by this operation.
    """

    id: int
    shard_count: int


class AutoShardedClient(Client):
    """Compatibility subclass of Client.

    It does not launch or coordinate multiple Gateway shards.

    Attributes:
        user: Authenticated account, inherited from Client.
        guilds: Cached guild snapshots, inherited from Client.
    """

    pass


class Shard:
    """Compatibility placeholder without an implemented shard lifecycle.

    Attributes:
        __dict__: Instance namespace retained for compatibility; no platform fields are defined.
    """

    pass


class EventType:
    """Compatibility placeholder without shard event orchestration.

    Attributes:
        __dict__: Instance namespace retained for compatibility; no platform fields are defined.
    """

    pass


class EventItem:
    """Compatibility placeholder without shard event orchestration.

    Attributes:
        __dict__: Instance namespace retained for compatibility; no platform fields are defined.
    """

    pass


__all__ = ("ShardInfo", "AutoShardedClient", "Shard", "EventType", "EventItem")
