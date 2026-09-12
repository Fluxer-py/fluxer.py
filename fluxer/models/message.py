"""Message helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .._endpoints import asset_url

from .._types import UNSET, UnsetType

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import process_embed_args

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..sticker import Sticker
    from ..file import File
    from ..http import HTTPClient
    from .attachment import Attachment
    from .member import GuildMember
    from .channel import Channel
    from .guild import Guild
    from .reaction import PartialEmoji, Reaction
    from .user import User


@dataclass(slots=True)
class MessageReference:
    """Reference to another Fluxer message.

    Attributes:
        message_id: Message identity supplied by the event or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
        type: Type used by this operation.
        attachment_ids: IDs of the attachment resources selected by this operation.
        embed_indices: Embed indices used by this operation.
    """

    message_id: int
    channel_id: int | None = None
    guild_id: int | None = None
    type: int | None = None
    attachment_ids: list[int] | None = None
    embed_indices: list[int] | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> MessageReference:
        """Build a MessageReference from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed MessageReference instance.
        """
        return cls(
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]) if data.get("channel_id") else None,
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            type=data.get("type"),
            attachment_ids=[int(item) for item in data["attachment_ids"]]
            if "attachment_ids" in data
            else None,
            embed_indices=[int(item) for item in data["embed_indices"]]
            if "embed_indices" in data
            else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this object's supported fields to a dictionary.

        Returns:
            The serialized representation with supported fields preserved.
        """
        data: dict[str, Any] = {"message_id": str(self.message_id)}
        if self.channel_id is not None:
            data["channel_id"] = str(self.channel_id)
        if self.guild_id is not None:
            data["guild_id"] = str(self.guild_id)
        if self.type is not None:
            data["type"] = self.type
        if self.attachment_ids is not None:
            data["attachment_ids"] = [str(item) for item in self.attachment_ids]
        if self.embed_indices is not None:
            data["embed_indices"] = self.embed_indices
        return data


@dataclass(slots=True)
class DeletedReferencedMessage:
    """Placeholder for a referenced message that is no longer available.

    Attributes:
        id: Identity of the object used by this operation.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
    """

    id: int | None = None
    channel_id: int | None = None
    guild_id: int | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> DeletedReferencedMessage:
        """Build a DeletedReferencedMessage from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed DeletedReferencedMessage instance.
        """
        return cls(
            id=int(data["id"]) if data.get("id") else None,
            channel_id=int(data["channel_id"]) if data.get("channel_id") else None,
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
        )


@dataclass(slots=True)
class PartialMessage:
    """Lightweight handle for a Fluxer message.

    Attributes:
        channel_id: Channel identity retained from the payload or operation context.
        id: Identity of the object used by this operation.
        jump_url: Build the message link using the client's discovered webapp service.
    """

    channel_id: int
    id: int
    _http: HTTPClient | None = field(default=None, repr=False)
    _channel: Channel | None = field(default=None, repr=False)
    _guild: Guild | None = field(default=None, repr=False)

    @property
    def jump_url(self) -> str:
        """Build the message link using the client's discovered webapp service.

        Returns:
            The result of this operation.
        """
        guild_id = self._guild.id if self._guild is not None else "@me"
        return asset_url(
            self._http, "webapp", f"channels/{guild_id}/{self.channel_id}/{self.id}"
        )

    async def fetch(self) -> Message:
        """Fetch.

        Returns:
            The result of this operation.
        """
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        data = await self._http.get_message(self.channel_id, self.id)
        message = Message.from_data(data, self._http)
        message._channel = self._channel
        message._cache_guild(self._guild)
        return message

    async def edit(
        self, content: str | None | UnsetType = UNSET, **kwargs: Any
    ) -> Message:
        """Edit.

        Args:
            content: Message text. On edits, omission preserves the text and None clears it.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
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
        """Delete.

        Returns:
            None.
        """
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        await self._http.delete_message(self.channel_id, self.id)

    async def pin(self) -> None:
        """Pin.

        Returns:
            None.
        """
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        await self._http.pin_message(self.channel_id, self.id)

    async def unpin(self) -> None:
        """Unpin.

        Returns:
            None.
        """
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        await self._http.unpin_message(self.channel_id, self.id)

    async def ack(self) -> None:
        """Ack.

        Returns:
            None.
        """
        if self._http is None:
            raise RuntimeError("PartialMessage is not bound to an HTTP client")
        if hasattr(self._http, "ack_message"):
            await self._http.ack_message(self.channel_id, self.id)
        else:
            await self._http.acknowledge_message(self.channel_id, self.id)


@dataclass(slots=True)
class Message:
    """Represents a message in a Fluxer channel.

    Attributes:
        id: The ID of the message.
        channel_id: The ID of the channel.
        content: The text of the message, empty when the message has only media.
        author: The user credited with the message.
        timestamp: Creation time derived from the message snowflake.
        edited_timestamp: Most recent edit time, or null when the message has never been edited.
        embeds: The previews resolved or supplied for the message.
        attachments: The files attached to the message.
        member: Guild-specific author membership, when supplied by the payload.
        mentions: The users the message actively mentions.
        pinned: Whether the message is pinned.
        reactions: Reaction summaries.
        referenced_message: Resolved referenced message without a nested `referenced_message` field.
        message_reference: Reply or forward reference.
        type: Message type.
        flags: Message flags.
        mention_everyone: Whether the message mentions everyone.
        tts: Whether the message requested text-to-speech.
        nonce: Caller-supplied message nonce, echoed to the sender as a string of 1 through 32 characters.
        webhook_id: Originating webhook ID, present only for a webhook-authored message.
        call: Call state attached to a call message.
        mention_roles: The IDs of the roles the message actively mentions.
        nsfw_emojis: IDs of the custom emojis in the message that are classified as explicit.
        mention_channels: The channels the message content links by ID.
        message_snapshots: The immutable copies captured for a forward.
        stickers: The stickers sent with the message.
        users: Users referenced by non-notifying content, embed, and snapshot text.
        created_at: Return the UTC creation time encoded in this object's snowflake.
        channel: The channel this message was sent in (if cached).
        guild: The guild this message was sent in (if cached).
        guild_id: Shortcut for the cached guild ID.
        jump_url: Build the message link using the client's discovered webapp service.
    """

    id: int
    channel_id: int
    content: str
    author: User
    timestamp: str
    edited_timestamp: str | None = None

    embeds: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    member: GuildMember | None = None
    mentions: list[User] = field(default_factory=list)
    pinned: bool = False
    reactions: list[Reaction] = field(default_factory=list)
    referenced_message: Message | DeletedReferencedMessage | None = None
    message_reference: MessageReference | None = None
    type: int = 0
    flags: int = 0
    mention_everyone: bool = False
    tts: bool = False
    nonce: str | None = None
    webhook_id: int | None = None
    call: dict[str, Any] | None = None
    _guild_id: int | None = None
    mention_roles: list[int] = field(default_factory=list)
    nsfw_emojis: list[int] = field(default_factory=list)
    mention_channels: list[dict[str, Any]] = field(default_factory=list)
    message_snapshots: list[dict[str, Any]] = field(default_factory=list)
    stickers: list[Sticker] = field(default_factory=list)
    users: list[User] = field(default_factory=list)

    _http: HTTPClient | None = field(default=None, repr=False)
    _channel: Channel | None = field(default=None, repr=False)
    _guild: Guild | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Message:
        """Build a Message from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Message instance.
        """
        from ..sticker import Sticker
        from .attachment import Attachment
        from .member import GuildMember
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
            member=GuildMember.from_data(
                {**data["member"], "user": data["author"]},
                http,
                guild_id=int(data["guild_id"])
                if data.get("guild_id") is not None
                else None,
            )
            if data.get("member") is not None
            else None,
            timestamp=data["timestamp"],
            edited_timestamp=data.get("edited_timestamp"),
            embeds=data.get("embeds", []),
            attachments=attachments,
            mentions=mentions,
            pinned=data.get("pinned", False),
            type=data.get("type", 0),
            flags=data.get("flags", 0),
            mention_everyone=data.get("mention_everyone", False),
            tts=data.get("tts", False),
            nonce=data.get("nonce"),
            webhook_id=int(data["webhook_id"])
            if data.get("webhook_id") is not None
            else None,
            call=data.get("call"),
            _guild_id=int(data["guild_id"])
            if data.get("guild_id") is not None
            else None,
            mention_roles=[int(item) for item in data.get("mention_roles", [])],
            nsfw_emojis=[int(item) for item in data.get("nsfw_emojis", [])],
            mention_channels=[dict(item) for item in data.get("mention_channels", [])],
            message_snapshots=[
                dict(item) for item in data.get("message_snapshots", [])
            ],
            stickers=[
                Sticker.from_data(item, http) for item in data.get("stickers", [])
            ],
            users=[User.from_data(item, http) for item in data.get("users", [])],
            _http=http,
            referenced_message=(
                Message.from_data(ref_data, http)
                if (ref_data := data.get("referenced_message"))
                else (
                    DeletedReferencedMessage.from_data(
                        {
                            "id": data.get("message_reference", {}).get("message_id"),
                            "channel_id": data.get("message_reference", {}).get(
                                "channel_id"
                            ),
                            "guild_id": data.get("message_reference", {}).get(
                                "guild_id"
                            ),
                        }
                    )
                    if "referenced_message" in data
                    else None
                )
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
        """Return the UTC creation time encoded in this object's snowflake.

        Returns:
            The result of this operation.
        """
        return snowflake_to_datetime(self.id)

    @property
    def channel(self) -> Channel | None:
        """The channel this message was sent in (if cached).

        Returns:
            The result of this operation.
        """
        return self._channel

    @property
    def guild(self) -> Guild | None:
        """The guild this message was sent in (if cached).

        Returns:
            The result of this operation.
        """
        return self._guild

    @property
    def guild_id(self) -> int | None:
        """Shortcut for the cached guild ID.

        Returns:
            The result of this operation.
        """
        return self._guild.id if self._guild else self._guild_id

    @property
    def jump_url(self) -> str:
        """Build the message link using the client's discovered webapp service.

        Returns:
            The result of this operation.
        """
        guild_id = self.guild_id if self.guild_id is not None else "@me"
        return asset_url(
            self._http, "webapp", f"channels/{guild_id}/{self.channel_id}/{self.id}"
        )

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
        if int(channel_id) == self.channel_id:
            msg._channel = self._channel
            msg._cache_guild(self._guild)
        return msg

    async def edit(
        self, content: str | None | UnsetType = UNSET, **kwargs: Any
    ) -> Message:
        """Edit this message.

        Args:
            content: Message text. On edits, omission preserves the text and None clears it.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
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
        """Delete this message.

        Returns:
            None.
        """
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

        Returns:
            None.
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

        Returns:
            None.
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

        Returns:
            None.
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

        Returns:
            None.
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

        Returns:
            None.
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

        Returns:
            None.
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
        """Set cached guild on this message and referenced_message, since replies can be assumed to be in same guild."""
        self._guild = guild
        if self.member is not None and guild is not None:
            self.member.guild_id = guild.id
        if isinstance(self.referenced_message, Message):
            self.referenced_message._cache_guild(guild)

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


__all__ = ("MessageReference", "DeletedReferencedMessage", "PartialMessage", "Message")
