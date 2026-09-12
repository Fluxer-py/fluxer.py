"""Channel helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from collections.abc import AsyncIterator, Callable, Generator
from typing import TYPE_CHECKING, Any

from ..utils import process_embed_args
from .user import User

from ..enums import ChannelType
from ..fluxer_models import (
    SearchAuthorType,
    SearchContentType,
    SearchEmbedType,
    SearchResponse,
    SearchSortBy,
    SearchSortOrder,
    parse_search_response,
)
from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..invite import Invite
    from ..client import Client
    from ..file import File
    from ..http import HTTPClient
    from ..voice import VoiceClient
    from .embed import Embed
    from .guild import Guild
    from .message import Message, PartialMessage


class _TypingContext:
    def __init__(self, channel: Channel) -> None:
        self.channel: Channel = channel

    def __await__(self) -> Generator[Any, None, None]:
        return self._send().__await__()

    async def __aenter__(self) -> _TypingContext:
        await self._send()
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def _send(self) -> None:
        await self.channel.trigger_typing()


@dataclass(slots=True)
class Channel:
    """Represents a Fluxer channel (text, DM, voice, category, etc.).

    Attributes:
        id: The ID of the channel.
        type: The type of the channel.
        name: The name of the channel, present for a guild channel and for a group direct message.
        guild_id: The ID of the guild, present only for a guild text, voice, category, or link channel.
        position: The sort position, present only for a guild channel.
        topic: The topic of the channel, present only for a guild text or voice channel.
        nsfw: Whether the channel has its own age restriction, present only for a guild channel.
        parent_id: The ID of the parent category, null when the channel sits at the top level.
        url: The destination URL, present only for a guild link channel.
        icon: The icon hash, present only for a group direct message.
        rtc_region: The ID of the selected RTC region, present only for a guild voice channel.
        last_pin_timestamp: The time a message was most recently pinned, or null when nothing has ever been pinned.
        content_warning_text: The content warning text stored on this channel, or null when the channel inherits.
        bitrate: The voice bitrate in bits per second, present only for a guild voice channel.
        user_limit: The configured member occupancy limit, present only for a guild voice channel.
        voice_connection_limit: The number of simultaneous voice connections one user may hold, present only for a guild voice channel.
        owner_id: The ID of the owner, present only for a group direct message.
        last_message_id: The ID of the most recent message, null when the channel has none.
        nsfw_override: Whether this channel overrides the inherited age restriction, or null when it inherits.
        content_warning_level: The content warning level stored on this channel, present only for a guild channel.
        rate_limit_per_user: The slowmode interval in seconds, present only for a guild text or voice channel.
        permission_overwrites: The overwrites applied to this channel, present only for a guild channel.
        nicks: The group direct message nicknames keyed by the decimal user ID (each 1-32 characters).
        recipients: The other recipients of a direct message or group direct message (max 49).
        guild: Guild.
        mention: Mention.
        created_at: Return the UTC creation time encoded in this object's snowflake.
        is_text_channel: Whether this is a guild text channel.
        is_voice_channel: Whether this is a voice channel.
        is_dm: Whether this is a DM channel.
        is_category: Whether this is a category channel.
    """

    id: int
    type: int
    name: str | None = None
    guild_id: int | None = None
    position: int | None = None
    topic: str | None = None
    nsfw: bool = False
    parent_id: int | None = None

    url: str | None = None
    icon: str | None = None
    rtc_region: str | None = None
    last_pin_timestamp: str | None = None
    content_warning_text: str | None = None
    bitrate: int | None = None
    user_limit: int | None = None
    voice_connection_limit: int | None = None
    owner_id: int | None = None
    last_message_id: int | None = None
    nsfw_override: bool | None = None
    content_warning_level: int = 0
    rate_limit_per_user: int = 0
    permission_overwrites: list[dict[str, Any]] = field(default_factory=list)
    nicks: dict[str, str] = field(default_factory=dict)
    recipients: list[User] = field(default_factory=list)

    _http: HTTPClient | None = field(default=None, repr=False)
    _guild: Guild | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Channel:
        """Build a Channel from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Channel instance.
        """
        return cls(
            id=int(data["id"]),
            type=data["type"],
            name=data.get("name"),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            position=data.get("position"),
            topic=data.get("topic"),
            nsfw=data.get("nsfw", False),
            parent_id=int(data["parent_id"]) if data.get("parent_id") else None,
            url=data.get("url", None),
            icon=data.get("icon", None),
            rtc_region=data.get("rtc_region", None),
            last_pin_timestamp=data.get("last_pin_timestamp", None),
            content_warning_text=data.get("content_warning_text", None),
            bitrate=data.get("bitrate", None),
            user_limit=data.get("user_limit", None),
            voice_connection_limit=data.get("voice_connection_limit", None),
            owner_id=int(data["owner_id"])
            if data.get("owner_id") is not None
            else None,
            last_message_id=int(data["last_message_id"])
            if data.get("last_message_id") is not None
            else None,
            nsfw_override=data.get("nsfw_override", None),
            content_warning_level=data.get("content_warning_level", 0),
            rate_limit_per_user=data.get("rate_limit_per_user", 0),
            permission_overwrites=list(data.get("permission_overwrites", [])),
            nicks=dict(data.get("nicks", {})),
            recipients=[
                User.from_data(user, http) for user in data.get("recipients", [])
            ],
            _http=http,
        )

    @property
    def guild(self) -> Guild | None:
        """Guild.

        Returns:
            The result of this operation.
        """
        return self._guild

    @property
    def mention(self) -> str:
        """Mention.

        Returns:
            The result of this operation.
        """
        return f"<#{self.id}>"

    @property
    def created_at(self) -> datetime:
        """Return the UTC creation time encoded in this object's snowflake.

        Returns:
            The result of this operation.
        """
        return snowflake_to_datetime(self.id)

    @property
    def is_text_channel(self) -> bool:
        """Whether this is a guild text channel.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.type == ChannelType.GUILD_TEXT

    @property
    def is_voice_channel(self) -> bool:
        """Whether this is a voice channel.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.type == ChannelType.GUILD_VOICE

    @property
    def is_dm(self) -> bool:
        """Whether this is a DM channel.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.type == ChannelType.DM

    @property
    def is_category(self) -> bool:
        """Whether this is a category channel.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.type == ChannelType.GUILD_CATEGORY

    async def send(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        message_reference: dict[str, Any] | None = None,
        allowed_mentions: Any | None = None,
        **kwargs: Any,
    ) -> Message:
        """Send a message to this channel.

        Args:
            content: Text content of the message.
            embed: A single embed to include.
            embeds: Multiple embeds to include.
            file: A single File object to attach.
            files: Multiple File objects to attach.
            message_reference: Reference to another message for replies.
            allowed_mentions: Controls which mentions notify users.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The created Message object.

        Examples:
            # Send a file from path
            from ..file import File
            await channel.send("Hello!", file=File("image.png"))

            # Send multiple files
            await channel.send("Files:", files=[File("a.txt"), File("b.txt")])

            # Send file with embed
            embed = Embed(title="Title")
            await channel.send(embed=embed, file=File("data.json"))
        """
        # Import here to avoid circular imports
        from .message import Message

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

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
            self.id,
            content=content,
            files=file_list,
            message_reference=message_reference,
            allowed_mentions=allowed_mentions,
            **combined_kwargs,
        )
        msg = Message.from_data(data, self._http)
        msg._channel = self
        msg._cache_guild(self._guild)
        return msg

    async def fetch_message(self, message_id: int | str) -> Message:
        """Fetch a message from this channel by ID.

        Args:
            message_id: The message ID to fetch.

        Returns:
            The fetched Message object.
        """
        from .message import Message

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        data = await self._http.get_message(self.id, message_id)
        msg = Message.from_data(data, self._http)
        msg._channel = self
        msg._cache_guild(self._guild)
        return msg

    async def fetch_messages(self, limit: int = 50) -> list[Message]:
        """Fetch recent messages from this channel.

        Args:
            limit: The maximum number of messages to fetch (default 50).

        Returns:
            A list of Message objects.
        """
        from .message import Message

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        data = await self._http.get_messages(self.id, limit=limit)
        msgs = [Message.from_data(msg_data, self._http) for msg_data in data]
        for msg in msgs:
            msg._channel = self
            msg._cache_guild(self._guild)
        return msgs

    def get_partial_message(self, message_id: int | str) -> PartialMessage:
        """Return a lightweight message handle for this channel.

        Args:
            message_id: Identity of the message used by this operation.

        Returns:
            The requested partial message.
        """
        from .message import PartialMessage

        return PartialMessage(
            channel_id=self.id,
            id=int(message_id),
            _http=self._http,
            _channel=self,
            _guild=self._guild,
        )

    async def history(
        self,
        *,
        limit: int = 50,
        before: int | str | None = None,
        after: int | str | None = None,
        around: int | str | None = None,
    ) -> AsyncIterator[Message]:
        """Iterate over recent messages in this channel.

        Args:
            limit: Maximum entries in the requested page; the route's documented bounds apply.
            before: Exclusive upper cursor for this operation's page.
            after: Exclusive lower message-ID cursor for the requested page.
            around: Message ID around which to centre the requested history page.

        Yields:
            Each message from the requested page, bound to known channel and guild context.
        """
        from .message import Message

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        data = await self._http.get_messages(
            self.id,
            limit=limit,
            before=before,
            after=after,
            around=around,
        )
        for msg_data in data:
            msg = Message.from_data(msg_data, self._http)
            msg._channel = self
            msg._cache_guild(self._guild)
            yield msg

    async def purge(
        self,
        *,
        limit: int = 50,
        check: Callable[[Message], bool] | None = None,
        before: int | str | None = None,
        after: int | str | None = None,
        around: int | str | None = None,
    ) -> list[Message]:
        """Delete recent messages selected by an optional predicate.

        Args:
            limit: Maximum entries in the requested page; the route's documented bounds apply.
            check: Condition used to select a message or accept an event.
            before: Exclusive upper cursor for this operation's page.
            after: Exclusive lower message-ID cursor for the requested page.
            around: Message ID around which to centre the requested history page.

        Returns:
            The result of this operation.
        """
        deleted: list[Message] = []
        async for message in self.history(
            limit=limit,
            before=before,
            after=after,
            around=around,
        ):
            if check is None or check(message):
                deleted.append(message)

        if deleted:
            if self._http is None:
                raise RuntimeError("Channel is not bound to an HTTP client")
            await self._http.delete_messages(
                self.id, [message.id for message in deleted]
            )
        return deleted

    async def fetch_pinned_messages(
        self,
        *,
        limit: int | None = None,
        before: str | None = None,
    ) -> list[Message]:
        """Fetch one page of pinned messages from this channel.

        Args:
            limit: Page size accepted by the pins endpoint.
            before: ISO8601 pin timestamp bounding this page.

        Returns:
            A list of pinned Message objects.
        """
        from .message import Message

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        data = await self._http.get_pinned_messages(self.id, limit=limit, before=before)
        msgs = [
            Message.from_data(msg_data.get("message", msg_data), self._http)
            for msg_data in data["items"]
        ]
        for msg in msgs:
            msg._channel = self
            msg._guild = self._guild
        return msgs

    async def ack_pins(self) -> None:
        """Acknowledge this channel's current pin state.

        Returns:
            None.
        """
        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")
        if hasattr(self._http, "ack_pins"):
            await self._http.ack_pins(self.id)
        else:
            await self._http.acknowledge_pins(self.id)

    async def invites(self) -> list[Invite]:
        """Fetch invites for this channel.

        Returns:
            The result of this operation.
        """
        from ..invite import Invite

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")
        data = await self._http.get_channel_invites(self.id)
        return [Invite.from_data(item, self._http) for item in data]

    async def create_invite(self, **kwargs: Any) -> Invite:
        """Create an invite for this channel.

        Args:
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        from ..invite import Invite

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")
        data = await self._http.create_channel_invite(self.id, **kwargs)
        return Invite.from_data(data, self._http)

    async def delete_messages(self, message_ids: list[int | str]) -> None:
        """Bulk delete messages in this channel.

        Args:
            message_ids: A list of message IDs to delete.

        Returns:
            None.
        """
        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        await self._http.delete_messages(self.id, message_ids)

    async def trigger_typing(self) -> None:
        """Trigger a typing indicator in this channel.

        Returns:
            None.
        """
        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        return await self._http.trigger_typing(self.id)

    def typing(self) -> _TypingContext:
        """Return a typing indicator helper for this channel.

        Returns:
            The result of this operation.
        """
        return _TypingContext(self)

    async def search_messages(
        self,
        *,
        hits_per_page: int | None = None,
        page: int | None = None,
        cursor: list[str] | None = None,
        min_id: int | str | None = None,
        max_id: int | str | None = None,
        content: str | None = None,
        contents: list[str] | None = None,
        exact_phrases: list[str] | None = None,
        exclude_channel_id: list[int | str] | None = None,
        author_id: list[int | str] | None = None,
        exclude_author_id: list[int | str] | None = None,
        author_type: list[SearchAuthorType] | None = None,
        exclude_author_type: list[SearchAuthorType] | None = None,
        mentions: list[int | str] | None = None,
        exclude_mentions: list[int | str] | None = None,
        mention_everyone: bool | None = None,
        pinned: bool | None = None,
        has: list[SearchContentType] | None = None,
        exclude_has: list[SearchContentType] | None = None,
        embed_type: list[SearchEmbedType] | None = None,
        exclude_embed_type: list[SearchEmbedType] | None = None,
        embed_provider: list[str] | None = None,
        exclude_embed_provider: list[str] | None = None,
        link_hostname: list[str] | None = None,
        exclude_link_hostname: list[str] | None = None,
        attachment_filename: list[str] | None = None,
        exclude_attachment_filename: list[str] | None = None,
        attachment_extension: list[str] | None = None,
        exclude_attachment_extension: list[str] | None = None,
        sort_by: SearchSortBy | None = None,
        sort_order: SearchSortOrder | None = None,
    ) -> SearchResponse:
        """Search messages in this channel using Fluxer's current scope.

        Args:
            hits_per_page: Maximum search hits requested in one result page.
            page: Page number passed to the search operation.
            cursor: Opaque search continuation values from the preceding result.
            min_id: Lower message-ID bound for search results.
            max_id: Upper message-ID bound for search results.
            content: Text content sent in the message.
            contents: Contents used by this operation.
            exact_phrases: Exact phrases used by this operation.
            exclude_channel_id: Identity of the exclude channel used by this operation.
            author_id: Identity of the author used by this operation.
            exclude_author_id: Identity of the exclude author used by this operation.
            author_type: Author type used by this operation.
            exclude_author_type: Author type values excluded from search results.
            mentions: Mentions used by this operation.
            exclude_mentions: Mentions values excluded from search results.
            mention_everyone: Mention everyone used by this operation.
            pinned: Pinned used by this operation.
            has: Has used by this operation.
            exclude_has: Has values excluded from search results.
            embed_type: Embed type used by this operation.
            exclude_embed_type: Embed type values excluded from search results.
            embed_provider: Embed provider used by this operation.
            exclude_embed_provider: Embed provider values excluded from search results.
            link_hostname: Link hostname used by this operation.
            exclude_link_hostname: Link hostname values excluded from search results.
            attachment_filename: Attachment filename used by this operation.
            exclude_attachment_filename: Attachment filename values excluded from search results.
            attachment_extension: Attachment extension used by this operation.
            exclude_attachment_extension: Attachment extension values excluded from search results.
            sort_by: Sort by used by this operation.
            sort_order: Sort order used by this operation.

        Returns:
            The result of this operation.
        """
        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")
        data = await self._http.search_messages(
            scope="current",
            context_channel_id=self.id,
            hits_per_page=hits_per_page,
            page=page,
            cursor=cursor,
            min_id=min_id,
            max_id=max_id,
            content=content,
            contents=contents,
            exact_phrases=exact_phrases,
            exclude_channel_id=exclude_channel_id,
            author_id=author_id,
            exclude_author_id=exclude_author_id,
            author_type=author_type,
            exclude_author_type=exclude_author_type,
            mentions=mentions,
            exclude_mentions=exclude_mentions,
            mention_everyone=mention_everyone,
            pinned=pinned,
            has=has,
            exclude_has=exclude_has,
            embed_type=embed_type,
            exclude_embed_type=exclude_embed_type,
            embed_provider=embed_provider,
            exclude_embed_provider=exclude_embed_provider,
            link_hostname=link_hostname,
            exclude_link_hostname=exclude_link_hostname,
            attachment_filename=attachment_filename,
            exclude_attachment_filename=exclude_attachment_filename,
            attachment_extension=attachment_extension,
            exclude_attachment_extension=exclude_attachment_extension,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return parse_search_response(data, self._http)

    async def connect(
        self,
        client: Client,
        *,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> VoiceClient:
        """Join this voice channel and return a connected VoiceClient.

        Requires fluxer.py[voice].

        Args:
            client: Client used by this operation.
            self_mute: Whether this voice connection starts with the local microphone muted.
            self_deaf: Whether this voice connection starts locally deafened.

        Returns:
            The result of this operation.
        """
        if not self.is_voice_channel:
            raise TypeError(f"Cannot connect to a non-voice channel (type={self.type})")
        if self.guild_id is None:
            raise ValueError("Cannot connect to a voice channel without a guild_id")
        return await client.join_voice(
            self.guild_id, self.id, self_mute=self_mute, self_deaf=self_deaf
        )

    def __eq__(self, other: object) -> bool:
        """Compare this object with another value using its identity semantics.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return isinstance(other, Channel) and self.id == other.id

    def __hash__(self) -> int:
        """Return the hash used for identity-based collection lookup.

        Returns:
            The result of this operation.
        """
        return hash(self.id)


__all__ = ("Channel",)
