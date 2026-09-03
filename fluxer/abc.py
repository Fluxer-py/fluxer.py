from __future__ import annotations

from typing import Protocol


class Snowflake(Protocol):
    id: int


class User(Snowflake, Protocol):
    pass


class PrivateChannel(Snowflake, Protocol):
    pass


class GuildChannel(Snowflake, Protocol):
    pass


class Messageable(Snowflake, Protocol):
    pass


class Connectable(Snowflake, Protocol):
    pass
