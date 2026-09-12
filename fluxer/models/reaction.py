"""Reaction helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from ..http import HTTPClient
    from .message import Message
    from .user import User


@dataclass(slots=True)
class PartialEmoji:
    """Represents a partial emoji (used in reactions).

    This can be either a custom emoji or a unicode emoji.

    Attributes:
        name: Name to assign or resolve in this operation.
        id: Identity of the object used by this operation.
        animated: Animated used by this operation.
        unicode: Unicode used by this operation.
        is_unicode_emoji: Whether this is a unicode emoji (vs custom emoji).
        is_custom_emoji: Whether this is a custom emoji.
    """

    name: str | None = None
    id: int | None = None
    animated: bool = False
    unicode: str | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> PartialEmoji:
        """Create a PartialEmoji from gateway data.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed PartialEmoji instance.
        """
        emoji_id = data.get("id")
        return cls(
            name=data.get("name"),
            id=int(emoji_id) if emoji_id else None,
            animated=data.get("animated", False),
            unicode=data.get("name") if not emoji_id else None,
        )

    @property
    def is_unicode_emoji(self) -> bool:
        """Whether this is a unicode emoji (vs custom emoji).

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.id is None

    @property
    def is_custom_emoji(self) -> bool:
        """Whether this is a custom emoji.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.id is not None

    def __str__(self) -> str:
        """String representation of the emoji.

        Returns:
            The result of this operation.
        """
        if self.is_unicode_emoji:
            return self.name or ""
        return f"<{'a' if self.animated else ''}:{self.name}:{self.id}>"

    def __eq__(self, other: object) -> bool:
        """Compare this object with another value using its identity semantics.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        if isinstance(other, PartialEmoji):
            return (
                self.id == other.id
                if self.id is not None
                else other.id is None and self.name == other.name
            )
        return False

    def __hash__(self) -> int:
        """Return the hash used for identity-based collection lookup.

        Returns:
            The result of this operation.
        """
        return hash(self.id) if self.id is not None else hash((None, self.name))


@dataclass(slots=True)
class Reaction:
    """Represents a reaction to a message.

    Attributes:
        emoji: The emoji used for this reaction
        count: Number of times this reaction was made
        me: Whether the current user reacted with this emoji
        message: The message this reaction is on.
    """

    emoji: PartialEmoji
    count: int = 0
    me: bool = False

    _message: Message | None = field(default=None, repr=False)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        message: Message | None = None,
    ) -> Reaction:
        """Create a Reaction from API data.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.
            message: Message supplying content and channel/guild context.

        Returns:
            A parsed Reaction instance.
        """
        emoji = PartialEmoji.from_data(data["emoji"])
        return cls(
            emoji=emoji,
            count=data.get("count", 0),
            me=data.get("me", False),
            _message=message,
            _http=http,
        )

    @property
    def message(self) -> Message | None:
        """The message this reaction is on.

        Returns:
            The result of this operation.
        """
        return self._message

    async def remove(self, user: User | int | str) -> None:
        """Remove this reaction from a specific user.

        Args:
            user: The user or user ID to remove the reaction from

        Raises:
            Forbidden: You don't have permission to remove this reaction
            NotFound: The message or reaction doesn't exist
            HTTPException: Removing the reaction failed

        Returns:
            None.
        """
        if not self._http or not self._message:
            raise RuntimeError("Cannot remove reaction without HTTPClient and Message")

        from .user import User as UserModel

        user_id = user.id if isinstance(user, UserModel) else user
        await self._http.delete_reaction(
            self._message.channel_id, self._message.id, self.emoji, user_id
        )

    async def clear(self) -> None:
        """Remove all instances of this reaction from the message.

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed

        Returns:
            None.
        """
        if not self._http or not self._message:
            raise RuntimeError("Cannot clear reaction without HTTPClient and Message")

        await self._http.delete_all_reactions_for_emoji(
            self._message.channel_id, self._message.id, self.emoji
        )

    def __str__(self) -> str:
        """Return the object's user-facing text representation.

        Returns:
            The result of this operation.
        """
        return str(self.emoji)

    def __eq__(self, other: object) -> bool:
        """Compare this object with another value using its identity semantics.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        if isinstance(other, Reaction):
            return self.emoji == other.emoji
        return False

    def __hash__(self) -> int:
        """Return the hash used for identity-based collection lookup.

        Returns:
            The result of this operation.
        """
        return hash(self.emoji)


@dataclass(slots=True)
class RawReactionActionEvent:
    """Represents a raw reaction add/remove event from the gateway.

    This event is dispatched even when the message is not in the internal cache.

    Attributes:
        message_id: Message identity supplied by the event or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
        user_id: Identity of the user used by this operation.
        emoji: Emoji used by this operation.
        event_type: Event type used by this operation.
    """

    message_id: int
    channel_id: int
    guild_id: int | None
    user_id: int
    emoji: PartialEmoji
    event_type: str  # "REACTION_ADD" or "REACTION_REMOVE"

    @classmethod
    def from_data(cls, data: dict[str, Any], event_type: str) -> RawReactionActionEvent:
        """Create a RawReactionActionEvent from gateway data.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            event_type: Event type used by this operation.

        Returns:
            A parsed RawReactionActionEvent instance.
        """
        emoji = PartialEmoji.from_data(data["emoji"])
        return cls(
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            user_id=int(data["user_id"]),
            emoji=emoji,
            event_type=event_type,
        )


@dataclass(slots=True)
class RawReactionClearEvent:
    """Represents a raw reaction clear event (all reactions removed from a message).

    Attributes:
        message_id: Message identity supplied by the event or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
    """

    message_id: int
    channel_id: int
    guild_id: int | None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> RawReactionClearEvent:
        """Create a RawReactionClearEvent from gateway data.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed RawReactionClearEvent instance.
        """
        return cls(
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
        )


@dataclass(slots=True)
class RawReactionClearEmojiEvent:
    """Represents a raw reaction clear emoji event (all reactions of a specific emoji removed).

    Attributes:
        message_id: Message identity supplied by the event or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
        emoji: Emoji used by this operation.
    """

    message_id: int
    channel_id: int
    guild_id: int | None
    emoji: PartialEmoji

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> RawReactionClearEmojiEvent:
        """Create a RawReactionClearEmojiEvent from gateway data.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed RawReactionClearEmojiEvent instance.
        """
        emoji = PartialEmoji.from_data(data["emoji"])
        return cls(
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            emoji=emoji,
        )


__all__ = (
    "PartialEmoji",
    "Reaction",
    "RawReactionActionEvent",
    "RawReactionClearEvent",
    "RawReactionClearEmojiEvent",
)
