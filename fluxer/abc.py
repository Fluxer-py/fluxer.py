"""Structural protocols describing the minimal identities used by this package.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from typing import Protocol


class Snowflake(Protocol):
    """Snowflake data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
    """

    id: int


class User(Snowflake, Protocol):
    """Structural user identity required by the existing interfaces.

    This protocol requires only an id; it does not promise profile fields.

    Attributes:
        id: Identity of the object used by this operation.
    """

    pass


class PrivateChannel(Snowflake, Protocol):
    """Private Channel data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
    """

    pass


class GuildChannel(Snowflake, Protocol):
    """Guild Channel data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
    """

    pass


class Messageable(Snowflake, Protocol):
    """Messageable data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
    """

    pass


class Connectable(Snowflake, Protocol):
    """Connectable data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
    """

    pass


__all__ = (
    "Snowflake",
    "User",
    "PrivateChannel",
    "GuildChannel",
    "Messageable",
    "Connectable",
)
