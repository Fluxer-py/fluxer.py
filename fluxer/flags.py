"""Flags helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .enums import Intents as Intents


class BaseFlags:
    """Integer flag wrapper without dynamic per-flag attribute access.

    Attributes:
        value: Stored integer value represented by this wrapper.
    """

    value: int

    def __init__(self, value: int = 0) -> None:
        """Initialize the base flags with the supplied configuration.

        Args:
            value: Value to convert, assign, or compare.
        """
        self.value = int(value)

    def __int__(self) -> int:
        """Return the stored integer value.

        Returns:
            The result of this operation.
        """
        return self.value


class MessageFlags(BaseFlags):
    """Message Flags data and behaviour.

    Attributes:
        value: Stored integer value represented by this wrapper.
    """

    pass


class PublicUserFlags(BaseFlags):
    """Public User Flags data and behaviour.

    Attributes:
        value: Stored integer value represented by this wrapper.
    """

    pass


class SystemChannelFlags(BaseFlags):
    """System Channel Flags data and behaviour.

    Attributes:
        value: Stored integer value represented by this wrapper.
    """

    pass


class MemberCacheFlags(BaseFlags):
    """Member Cache Flags data and behaviour.

    Attributes:
        value: Stored integer value represented by this wrapper.
    """

    @classmethod
    def none(cls) -> "MemberCacheFlags":
        """None.

        Returns:
            The result of this operation.
        """
        return cls(0)

    @classmethod
    def all(cls) -> "MemberCacheFlags":
        """All.

        Returns:
            The result of this operation.
        """
        return cls(1)


__all__ = (
    "BaseFlags",
    "MessageFlags",
    "PublicUserFlags",
    "SystemChannelFlags",
    "MemberCacheFlags",
    "Intents",
)
