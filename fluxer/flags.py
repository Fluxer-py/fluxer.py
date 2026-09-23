"""Flags helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .enums import Intents as Intents


class BaseFlags:
    """Integer flag wrapper retaining the complete raw mask.

    Attributes:
        value: Stored integer value represented by this wrapper.
    """

    value: int

    def __init__(self, value: int | BaseFlags = 0) -> None:
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
    """Fluxer message flags.

    Attributes:
        value: Stored integer value represented by this wrapper.
        suppress_embeds: Whether embed rendering is suppressed.
        suppress_notifications: Whether ordinary mention notifications are suppressed.
        voice_message: Whether the message contains a voice recording.
    """

    @property
    def suppress_embeds(self) -> bool:
        """Return whether embed rendering is suppressed.

        Returns:
            Whether the suppress-embeds bit is set.
        """
        return bool(self.value & (1 << 2))

    @property
    def suppress_notifications(self) -> bool:
        """Return whether ordinary mention notifications are suppressed.

        Returns:
            Whether the suppress-notifications bit is set.
        """
        return bool(self.value & (1 << 12))

    @property
    def voice_message(self) -> bool:
        """Return whether the message contains a voice recording.

        Returns:
            Whether the voice-message bit is set.
        """
        return bool(self.value & (1 << 13))


class AttachmentFlags(BaseFlags):
    """Fluxer attachment flags.

    Attributes:
        value: Stored integer value represented by this wrapper.
        is_spoiler: Whether the attachment is presented as a spoiler.
        contains_explicit_media: Whether media inspection marked it explicit.
        is_animated: Whether the attachment is animated.
    """

    @property
    def is_spoiler(self) -> bool:
        """Return whether the attachment is presented as a spoiler.

        Returns:
            Whether the spoiler bit is set.
        """
        return bool(self.value & (1 << 3))

    @property
    def contains_explicit_media(self) -> bool:
        """Return whether the attachment contains explicit media.

        Returns:
            Whether the explicit-media bit is set.
        """
        return bool(self.value & (1 << 4))

    @property
    def is_animated(self) -> bool:
        """Return whether the attachment is animated.

        Returns:
            Whether the animated bit is set.
        """
        return bool(self.value & (1 << 5))


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
    "AttachmentFlags",
    "PublicUserFlags",
    "SystemChannelFlags",
    "MemberCacheFlags",
    "Intents",
)
