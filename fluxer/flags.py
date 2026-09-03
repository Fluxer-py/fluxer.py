from __future__ import annotations

from .enums import Intents as Intents


class BaseFlags:
    def __init__(self, value: int = 0) -> None:
        self.value = int(value)

    def __int__(self) -> int:
        return self.value


class MessageFlags(BaseFlags):
    pass


class PublicUserFlags(BaseFlags):
    pass


class SystemChannelFlags(BaseFlags):
    pass


class MemberCacheFlags(BaseFlags):
    @classmethod
    def none(cls) -> "MemberCacheFlags":
        return cls(0)

    @classmethod
    def all(cls) -> "MemberCacheFlags":
        return cls(1)
