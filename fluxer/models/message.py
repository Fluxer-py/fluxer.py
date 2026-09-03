from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fluxer.utils import process_embed_args

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..file import File
    from ..http import HTTPClient
    from .attachment import Attachment
    from .channel import Channel
    from .guild import Guild
    from .reaction import PartialEmoji, Reaction
    from .user import User


@dataclass(slots=True)
class MessageReference:
    """Reference to another Fluxer message."""

    message_id: int
    channel_id: int | None = None
    guild_id: int | None = None
    type: int | None = None
    attachment_ids: list[int] = field(default_factory=list)
    embed_indices: list[int] = field(default_factory=list)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> MessageReference:
        return cls(
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]) if data.get("channel_id") else None,
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            type=data.get("type"),
            attachment_ids=[int(item) for item in data.get("attachment_ids", [])],
            embed_indices=[int(item) for item in data.get("embed_indices", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"message_id": str(self.message_id)}
        if self.channel_id is not None:
            data["channel_id"] = str(self.channel_id)
        if self.guild_id is not None:
            data["guild_id"] = str(self.guild_id)
        if self.type is not None:
            data["type"] = self.type
        if self.attachment_ids:
            data["attachment_ids"] = [str(item) for item in self.attachment_ids]
        if self.embed_indices:
            data["embed_indices"] = self.embed_indices
        return data


@dataclass(slots=True)
class DeletedReferencedMessage:
    """Placeholder for a referenced message that is no longer available."""

    id: int | None = None
    channel_id: int | None = None
    guild_id: int | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> DeletedReferencedMessage:
        return cls(
            id=int(data["id"]) if data.get("id") else None,
            channel_id=int(data["channel_id"]) if data.get("channel_id") else None,
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
        )


@dataclass(slots=True)
class PartialMessage:
    """Lightweight handle for a Fluxer message."""

    channel_id: int
    id: int
    _http: HTTPClient | None = field(default=None, repr=False)
    _channel: Channel | None = field(default=None, repr=False)
    _guild: Guild | None = field(default=None, repr=False)

    @property
    def jump_url(self) -> str:
        guild_id = self._guild.id if self._guild is not None else "@me"
        return f"https://fluxer.app/channels/{guild_id}/{self.channel_id}/{self.id}"

    async def fetch(self) -> Message:
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        data = await self._http.get_message(self.channel_id, self.id)
        message = Message.from_data(data, self._http)
        message._channel = self._channel
        message._cache_guild(self._guild)
        return message

    async def edit(self, content: str | None = None, **kwargs: Any) -> Message:
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        kwargs = process_embed_args(kwargs)
        data = await self._http.edit_message(
            self.channel_id,
            self.id,
            content=content,
            **kwargs,
        )
        message = Message.from_data(data, self._http)
        message._channel = self._channel
        message._cache_guild(self._guild)
        return message

    async def delete(self) -> None:
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        await self._http.delete_message(self.channel_id, self.id)

    async def pin(self) -> None:
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        await self._http.pin_message(self.channel_id, self.id)

    async def unpin(self) -> None:
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        await self._http.unpin_message(self.channel_id, self.id)

    async def ack(self) -> None:
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        if hasattr(self._http, "ack_message"):
            await self._http.ack_message(self.channel_id, self.id)
        else:
            await self._http.acknowledge_message(self.channel_id, self.id)


@dataclass(slots=True)
class Message:
    """Represents a message in a Fluxer channel."""

    id: int
    channel_id: int
    content: str
    author: User
    timestamp: str
    edited_timestamp: str | None = None

    embeds: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    mentions: list[User] = field(default_factory=list)
    pinned: bool = False
    reactions: list[Reaction] = field(default_factory=list)
    referenced_message: Message | None = None
    message_reference: MessageReference | None = None

    _http: HTTPClient | None = field(default=None, repr=False)
    _channel: Channel | None = field(default=None, repr=False)
    _guild: Guild | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Message:
        from .attachment import Attachment
        from .reaction import Reaction
        from .user import User

        author = User.from_data(data["author"], http)
        mentions = [User.from_data(u, http) for u in data.get("mentions", [])]
        attachments = [Attachment.from_data(a) for a in data.get("attachments", [])]

        # Create message first without reactions
        message = cls(
            id=int(data["id"]),
            channel_id=int(data["channel_id"]),
            content=data.get("content", ""),
            author=author,
            timestamp=data["timestamp"],
            edited_timestamp=data.get("edited_timestamp"),
            embeds=data.get("embeds", []),
            attachments=attachments,
            mentions=mentions,
            pinned=data.get("pinned", False),
            _http=http,
            referenced_message=(
                Message.from_data(ref_data, http)
                if (ref_data := data.get("referenced_message"))
                else None
            ),
            message_reference=(
                MessageReference.from_data(ref_data)
                if (ref_data := data.get("message_reference"))
                else None
            ),
        )

        # Parse reactions and link them to the message
        reactions_data = data.get("reactions", [])
        message.reactions = [
            Reaction.from_data(r, http=http, message=message) for r in reactions_data
        ]

        return message

    @property
    def created_at(self) -> datetime:
        return snowflake_to_datetime(self.id)

    @property
    def channel(self) -> Channel | None:
        """The channel this message was sent in (if cached)."""
        return self._channel

    @property
    def guild(self) -> Guild | None:
        """The guild this message was sent in (if cached)."""
        return self._guild

    @property
    def guild_id(self) -> int | None:
        """Shortcut for the cached guild ID."""
        return self._guild.id if self._guild else None

    @property
    def jump_url(self) -> str:
        guild_id = self.guild_id if self.guild_id is not None else "@me"
        return f"https://fluxer.app/channels/{guild_id}/{self.channel_id}/{self.id}"

    async def send(
        self,
        content: str | None = None,
        *,
        embed: Any | None = None,
        embeds: list[Any] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        **kwargs: Any,
    ) -> Message:
        """Send a message to the same channel (without replying).

        Args:
            content: The message content.
            embed: A single embed to include.
            embeds: Multiple embeds to include.
            file: A single File object to attach.
            files: Multiple File objects to attach.
            **kwargs: Additional arguments to pass to send_message

        Returns:
            The created Message object.
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")

        # Auto-convert single embed to embeds list
        combined_kwargs = {"embed": embed, "embeds": embeds, **kwargs}
        combined_kwargs = process_embed_args(combined_kwargs)

        # Handle file/files parameter - convert File objects to dict format
        file_list: list[dict[str, Any]] | None = None
        if file is not None:
            file_list = [file.to_dict()]
        elif files is not None:
            file_list = [f.to_dict() for f in files]

        data = await self._http.send_message(
            self.channel_id,
            content=content,
            files=file_list,
            **combined_kwargs,
        )
        msg = Message.from_data(data, self._http)
        msg._channel = self._channel
        msg._cache_guild(self._guild)
        return msg

    async def reply(
        self,
        content: str | None = None,
        *,
        embed: Any | None = None,
        embeds: list[Any] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        **kwargs: Any,
    ) -> Message:
        """Reply to this message with a message reference.

        Args:
            content: The message content.
            embed: A single embed to include.
            embeds: Multiple embeds to include.
            file: A single File object to attach.
            files: Multiple File objects to attach.
            **kwargs: Additional arguments to pass to send_message

        Returns:
            The created Message object.
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")

        # Auto-convert single embed to embeds list
        combined_kwargs = {"embed": embed, "embeds": embeds, **kwargs}
        combined_kwargs = process_embed_args(combined_kwargs)

        # Handle file/files parameter - convert File objects to dict format
        file_list: list[dict[str, Any]] | None = None
        if file is not None:
            file_list = [file.to_dict()]
        elif files is not None:
            file_list = [f.to_dict() for f in files]

        # Create message reference to reply to this message
        message_reference = {
            "message_id": str(self.id),
            "channel_id": str(self.channel_id),
        }
        if self.guild_id:
            message_reference["guild_id"] = str(self.guild_id)

        data = await self._http.send_message(
            self.channel_id,
            content=content,
            message_reference=message_reference,
            files=file_list,
            **combined_kwargs,
        )
        msg = Message.from_data(data, self._http)
        msg._channel = self._channel
        msg._cache_guild(self._guild)
        return msg

    async def send_to_channel(
        self,
        channel_id: int | str,
        content: str | None = None,
        *,
        embed: Any | None = None,
        embeds: list[Any] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        **kwargs: Any,
    ) -> Message:
        """Send a message to a different channel.

        This is a convenience method to send to another channel from the context
        of this message (e.g., forwarding content or sending notifications).

        Args:
            channel_id: The target channel ID.
            content: The message content.
            embed: A single embed to include.
            embeds: Multiple embeds to include.
            file: A single File object to attach.
            files: Multiple File objects to attach.
            **kwargs: Additional arguments to pass to send_message

        Returns:
            The created Message object.
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")

        # Auto-convert single embed to embeds list
        combined_kwargs = {"embed": embed, "embeds": embeds, **kwargs}
        combined_kwargs = process_embed_args(combined_kwargs)

        # Handle file/files parameter - convert File objects to dict format
        file_list: list[dict[str, Any]] | None = None
        if file is not None:
            file_list = [file.to_dict()]
        elif files is not None:
            file_list = [f.to_dict() for f in files]

        data = await self._http.send_message(
            channel_id, content=content, files=file_list, **combined_kwargs
        )
        msg = Message.from_data(data, self._http)
        msg._cache_guild(self._guild)
        return msg

    async def edit(self, content: str | None = None, **kwargs: Any) -> Message:
        """Edit this message."""
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        kwargs = process_embed_args(kwargs)
        data = await self._http.edit_message(
            self.channel_id, self.id, content=content, **kwargs
        )
        msg = Message.from_data(data, self._http)
        msg._channel = self._channel
        msg._cache_guild(self._guild)
        return msg

    async def delete(self) -> None:
        """Delete this message."""
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.delete_message(self.channel_id, self.id)

    async def add_reaction(self, emoji: str | PartialEmoji) -> None:
        """Add a reaction to this message.

        Args:
            emoji: The emoji to react with (unicode string or PartialEmoji)

        Raises:
            Forbidden: You don't have permission to add reactions
            NotFound: The message doesn't exist
            HTTPException: Adding the reaction failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.add_reaction(self.channel_id, self.id, emoji)

    async def remove_reaction(
        self, emoji: str | PartialEmoji, user: User | int | str = "@me"
    ) -> None:
        """Remove a reaction from this message.

        Args:
            emoji: The emoji to remove (unicode string or PartialEmoji)
            user: The user or user ID to remove the reaction from (default: @me)

        Raises:
            Forbidden: You don't have permission to remove this reaction
            NotFound: The message or reaction doesn't exist
            HTTPException: Removing the reaction failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")

        from .user import User as UserModel

        user_id = user.id if isinstance(user, UserModel) else user
        await self._http.delete_reaction(self.channel_id, self.id, emoji, user_id)

    async def clear_reactions(self) -> None:
        """Remove all reactions from this message.

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.delete_all_reactions(self.channel_id, self.id)

    async def clear_reaction(self, emoji: str | PartialEmoji) -> None:
        """Remove all reactions of a specific emoji from this message.

        Args:
            emoji: The emoji to clear all reactions for (unicode string or PartialEmoji)

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.delete_all_reactions_for_emoji(self.channel_id, self.id, emoji)

    async def pin(self) -> None:
        """Pin this message to the channel.

        Raises:
            Forbidden: You don't have permission to pin messages
            NotFound: The message doesn't exist
            HTTPException: Pinning the message failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.pin_message(self.channel_id, self.id)
        self.pinned = True

    async def unpin(self) -> None:
        """Unpin this message from the channel.

        Raises:
            Forbidden: You don't have permission to unpin messages
            NotFound: The message doesn't exist
            HTTPException: Unpinning the message failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.unpin_message(self.channel_id, self.id)
        self.pinned = False

    # Internal methods for handling reaction updates from gateway events
    def _add_reaction(
        self, data: dict[str, Any], emoji: PartialEmoji, user_id: int
    ) -> Reaction:
        """Internal method to add a reaction to this message from gateway data.

        Args:
            data: Gateway reaction data
            emoji: The emoji that was reacted with
            user_id: The user who reacted

        Returns:
            The Reaction object that was added or updated
        """
        from .reaction import Reaction

        # Find existing reaction with this emoji
        for reaction in self.reactions:
            if reaction.emoji == emoji:
                # Update existing reaction
                reaction.count += 1
                if user_id == getattr(self._http, "_user_id", None):
                    reaction.me = True
                return reaction

        # Create new reaction
        reaction = Reaction(
            emoji=emoji, count=1, me=False, _message=self, _http=self._http
        )
        self.reactions.append(reaction)
        return reaction

    def _remove_reaction(
        self, data: dict[str, Any], emoji: PartialEmoji, user_id: int
    ) -> Reaction:
        """Internal method to remove a reaction from this message from gateway data.

        Args:
            data: Gateway reaction data
            emoji: The emoji that was removed
            user_id: The user who removed their reaction

        Returns:
            The Reaction object that was updated or removed
        """
        # Find the reaction
        for i, reaction in enumerate(self.reactions):
            if reaction.emoji == emoji:
                reaction.count -= 1
                if user_id == getattr(self._http, "_user_id", None):
                    reaction.me = False

                # Remove reaction if count reaches 0
                if reaction.count <= 0:
                    self.reactions.pop(i)

                return reaction

        raise ValueError(f"Reaction {emoji} not found on message")

    def _cache_guild(self, guild: Guild | None) -> None:
        """Set cached guild on this message and referenced_message, since replies can be assumed to be in same guild"""
        self._guild = guild
        if self.referenced_message is not None:
            self.referenced_message._guild = guild

    def _clear_emoji(self, emoji: PartialEmoji) -> Reaction | None:
        """Internal method to clear all reactions of a specific emoji.

        Args:
            emoji: The emoji to clear

        Returns:
            The Reaction object that was removed, or None if not found
        """
        for i, reaction in enumerate(self.reactions):
            if reaction.emoji == emoji:
                return self.reactions.pop(i)
        return None
