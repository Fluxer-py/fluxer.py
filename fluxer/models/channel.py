"""Channel helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .._model_factory import _snapshot

from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import AsyncIterator, Callable, Generator
from typing import TYPE_CHECKING, Any

from .._types import UNSET, UnsetType
from ..permissions import (
    ChannelPermissionOverwrite,
    PermissionOverwrite,
    PermissionOverwritePayload,
    PermissionOverwriteType,
    Permissions,
    _effective_permissions,
    parse_permission_overwrite,
)
from ..utils import process_embed_args
from .member import GuildMember
from .message import Message, PartialMessage
from .role import Role
from .thread import ThreadArchiveDuration, ThreadMember, ThreadMetadata
from .user import User

from ..enums import THREAD_CHANNEL_TYPES, ChannelType
from ..invite import Invite
from ..fluxer_models import (
    SearchAuthorType,
    SearchContentType,
    SearchEmbedType,
    SearchResponse,
    SearchSortBy,
    SearchSortOrder,
    parse_search_response,
)
from ..utils import datetime_to_snowflake, snowflake_to_datetime

if TYPE_CHECKING:
    from ..state import ConnectionState
    from ..client import Client
    from ..file import File
    from ..http import HTTPClient
    from ..voice import VoiceClient
    from .embed import Embed
    from .guild import Guild


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
        icon_hash: The icon hash, present only for a group direct message.
        rtc_region: The ID of the selected RTC region, present only for a guild voice channel.
        last_pin_timestamp: The time a message was most recently pinned, or null when nothing has ever been pinned.
        content_warning_text: The content warning text stored on this channel, or null when the channel inherits.
        bitrate: The voice bitrate in bits per second, present only for a guild voice channel.
        user_limit: The configured member occupancy limit, present only for a guild voice channel.
        voice_connection_limit: The number of simultaneous voice connections one user may hold, present only for a guild voice channel.
        owner_id: The ID of the owner of a group direct message, or the creator of a thread.
        last_message_id: The ID of the most recent message, null when the channel has none.
        nsfw_override: Whether this channel overrides the inherited age restriction, or null when it inherits.
        content_warning_level: The content warning level stored on this channel, present only for a guild channel.
        rate_limit_per_user: The slowmode interval in seconds, for a guild text or voice channel or a thread.
        permission_overwrites: The overwrites applied to this channel, present only for a guild channel.
        nicks: The group direct message nicknames keyed by the decimal user ID (each 1-32 characters).
        recipients: The other recipients of a direct message or group direct message (max 49).
        flags: Channel flags; on a thread only ``PINNED`` is ever set.
        thread_metadata: Archive and lock state, present only on a thread.
        message_count: Messages in a thread, excluding a forum post's first message.
        total_message_sent: Messages ever sent in a thread.
        member_count: Thread members, capped at 50 by Fluxer.
        applied_tags: Forum tag IDs applied to a forum or media post.
        is_thread: Whether this channel is a thread.
        archived: Whether this thread is archived.
        locked: Whether this thread is locked.
        parent: The cached parent channel or category.
        me: The current user's thread membership, when known.
        thread_members: Cached thread memberships, populated by member events.
        slowmode_delay: Alias of ``rate_limit_per_user``.
        owner: The cached guild member who created this thread.
        threads: The cached threads whose parent is this channel.
        starter_message: The cached message this thread was started from.
        guild: Guild.
        mention: Mention.
        created_at: Return the UTC creation time encoded in this object's snowflake.
        is_text_channel: Whether this is a guild text channel.
        is_voice_channel: Whether this is a voice channel.
        is_dm: Whether this is a DM channel.
        is_category: Whether this is a category channel.
        overwrites: Immutable typed permission overwrite records.
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
    icon_hash: str | None = None
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
    permission_overwrites: list[PermissionOverwritePayload] = field(
        default_factory=list
    )
    nicks: dict[str, str] = field(default_factory=dict)
    recipients: list[User] = field(default_factory=list)
    flags: int = 0
    thread_metadata: ThreadMetadata | None = None
    message_count: int | None = None
    total_message_sent: int | None = None
    member_count: int | None = None
    applied_tags: list[int] = field(default_factory=list)

    _state: ConnectionState | None = field(default=None, repr=False, compare=False)
    _http: HTTPClient | None = field(default=None, repr=False)
    _guild: Guild | None = field(default=None, repr=False)
    _me: ThreadMember | None = field(default=None, repr=False, compare=False)
    _thread_members: dict[int, ThreadMember] = field(
        default_factory=dict, repr=False, compare=False
    )

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
            icon_hash=data.get("icon", None),
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
            permission_overwrites=[
                parse_permission_overwrite(item)
                for item in data.get("permission_overwrites", [])
            ],
            nicks=dict(data.get("nicks", {})),
            recipients=[
                User.from_data(user, http) for user in data.get("recipients", [])
            ],
            flags=int(data.get("flags", 0) or 0),
            thread_metadata=ThreadMetadata.from_data(data["thread_metadata"])
            if isinstance(data.get("thread_metadata"), dict)
            else None,
            message_count=data.get("message_count"),
            total_message_sent=data.get("total_message_sent"),
            member_count=data.get("member_count"),
            applied_tags=[int(tag) for tag in data.get("applied_tags", [])],
            _http=http,
            _state=getattr(http, "_state", None),
        )

    @property
    def guild(self) -> Guild | None:
        """Guild.

        Returns:
            The result of this operation.
        """
        if self._guild is not None:
            return self._guild
        return (
            self._state.guilds.get(self.guild_id)
            if self._state is not None and self.guild_id is not None
            else None
        )

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

    @property
    def is_thread(self) -> bool:
        """Whether this channel is an announcement, public, or private thread.

        Returns:
            Whether the channel type is a thread type.
        """
        return self.type in THREAD_CHANNEL_TYPES

    @property
    def archived(self) -> bool:
        """Whether this thread is archived; always False for other channels.

        Returns:
            The archive flag from the thread metadata.
        """
        return self.thread_metadata is not None and self.thread_metadata.archived

    @property
    def locked(self) -> bool:
        """Whether this thread is locked; always False for other channels.

        Returns:
            The lock flag from the thread metadata.
        """
        return self.thread_metadata is not None and self.thread_metadata.locked

    @property
    def parent(self) -> Channel | None:
        """The cached parent: a thread's channel, or a channel's category.

        Returns:
            The parent channel, or None when there is none or it is not cached.
        """
        if self.parent_id is None or self._state is None:
            return None
        return self._state.channels.get(self.parent_id)

    @property
    def me(self) -> ThreadMember | None:
        """The current user's membership in this thread.

        Returns:
            The membership, or None when the user is not a member or it is unknown.
        """
        return self._me

    @property
    def thread_members(self) -> list[ThreadMember]:
        """Thread memberships cached from Thread Members Update events.

        Fluxer sends no full thread roster on connect, so this list holds only the
        members seen joining since the thread was cached.

        Returns:
            The cached memberships.
        """
        return list(self._thread_members.values())

    @property
    def slowmode_delay(self) -> int:
        """Seconds a member must wait between messages; alias of ``rate_limit_per_user``.

        Returns:
            The slowmode interval in seconds, 0 when slowmode is off.
        """
        return self.rate_limit_per_user

    @property
    def owner(self) -> GuildMember | None:
        """The cached guild member who created this thread.

        Returns:
            The member, or None for a non-thread channel or an uncached member.
        """
        if not self.is_thread or self.owner_id is None:
            return None
        guild = self.guild
        return guild.get_member(self.owner_id) if guild is not None else None

    @property
    def threads(self) -> list[Channel]:
        """The cached threads whose parent is this channel.

        Returns:
            The cached threads; archived threads leave the cache.
        """
        guild = self.guild
        if guild is None:
            return []
        return [t for t in guild._threads.values() if t.parent_id == self.id]

    def get_thread(self, thread_id: int, /) -> Channel | None:
        """Look up a cached thread of this channel.

        Args:
            thread_id: The thread ID.

        Returns:
            The thread, or None when it is not cached or has another parent.
        """
        guild = self.guild
        thread = guild.get_thread(thread_id) if guild is not None else None
        if thread is None or thread.parent_id != self.id:
            return None
        return thread

    @property
    def starter_message(self) -> Message | None:
        """The cached message this thread was started from.

        A thread started from a message shares that message's ID.

        Returns:
            The message, or None when it is not cached.
        """
        if not self.is_thread or self._state is None:
            return None
        return self._state.messages.get(self.id)

    @property
    def overwrites(self) -> list[ChannelPermissionOverwrite]:
        """Return immutable typed permission overwrites for this channel.

        Returns:
            The channel's overwrite records in payload order.
        """
        return [
            ChannelPermissionOverwrite.from_data(overwrite)
            for overwrite in self.permission_overwrites
        ]

    def _require_guild_context(self) -> Guild:
        if self.guild_id is None:
            raise TypeError(
                "Permission overwrites are available only on guild channels"
            )
        guild = self.guild
        if guild is None:
            raise RuntimeError("Channel is missing its bound guild context")
        return guild

    def _resolve_overwrite_target(
        self,
        target: Role | GuildMember | User | int,
        overwrite_type: PermissionOverwriteType | int | None,
    ) -> tuple[int, PermissionOverwriteType]:
        guild = self._require_guild_context()
        explicit_type: PermissionOverwriteType | None = None
        if overwrite_type is not None:
            if isinstance(overwrite_type, bool):
                raise TypeError("Overwrite type must be ROLE or MEMBER")
            try:
                explicit_type = PermissionOverwriteType(overwrite_type)
            except (TypeError, ValueError) as exc:
                raise ValueError("Overwrite type must be ROLE or MEMBER") from exc

        inferred_type: PermissionOverwriteType
        target_id: int
        target_guild_id: int | None = None
        if isinstance(target, Role):
            target_id = target.id
            target_guild_id = target.guild_id
            inferred_type = PermissionOverwriteType.ROLE
        elif isinstance(target, GuildMember):
            target_id = target.user.id
            target_guild_id = target.guild_id
            inferred_type = PermissionOverwriteType.MEMBER
        elif isinstance(target, User):
            target_id = target.id
            inferred_type = PermissionOverwriteType.MEMBER
        elif isinstance(target, int) and not isinstance(target, bool):
            target_id = target
            if explicit_type is None:
                raise TypeError("A bare target ID requires an overwrite type")
            inferred_type = explicit_type
        else:
            raise TypeError("Target must be a Role, GuildMember, User, or integer ID")

        if target_id <= 0:
            raise ValueError("Overwrite target ID must be a positive integer snowflake")
        if target_guild_id is not None and target_guild_id != guild.id:
            raise ValueError("Overwrite target belongs to a different guild")
        if explicit_type is not None and explicit_type != inferred_type:
            raise ValueError("Explicit overwrite type conflicts with the target object")
        return target_id, inferred_type

    def overwrites_for(
        self,
        target: Role | GuildMember | User | int,
        *,
        type: PermissionOverwriteType | int | None = None,
    ) -> PermissionOverwrite:
        """Return the overwrite stored for one role or member.

        Args:
            target: Role, member, user, or explicitly typed target ID.
            type: Target kind required for a bare integer ID.

        Returns:
            A mutable copy of the stored overwrite, or an empty overwrite.

        Raises:
            TypeError: The channel or target kind cannot hold an overwrite.
            RuntimeError: The channel is missing guild context.
            ValueError: The target type conflicts or belongs to another guild.
        """
        target_id, target_type = self._resolve_overwrite_target(target, type)
        for overwrite in self.overwrites:
            if overwrite.id == target_id and overwrite.type == target_type:
                return overwrite.to_overwrite()
        return PermissionOverwrite()

    def permissions_for(self, member_or_user: GuildMember | User) -> Permissions:
        """Calculate effective channel permissions from the bound guild cache.

        Args:
            member_or_user: Guild membership or user to resolve in the guild cache.

        Returns:
            The effective 64-bit permission mask, or an empty mask for a user
            established as a nonmember by a complete member cache.

        Raises:
            TypeError: The channel is private or the argument is unsupported.
            RuntimeError: Required membership, ownership, roles, or channel context is incomplete.

        Note:
            Threads have no overwrites of their own; Fluxer resolves them with
            their parent channel's permissions, so this delegates to ``parent``.
        """
        if self.is_thread:
            parent = self.parent
            if parent is None:
                raise RuntimeError("Thread parent channel is not cached")
            return parent.permissions_for(member_or_user)
        guild = self._require_guild_context()
        member: GuildMember | None
        if isinstance(member_or_user, GuildMember):
            if member_or_user.guild_id not in (None, guild.id):
                return Permissions(0)
            member = member_or_user
        elif isinstance(member_or_user, User):
            member = guild.get_member(member_or_user.id)
            if member is None:
                if not guild.member_cache_complete:
                    raise RuntimeError(
                        "Guild member cache is incomplete; supply a GuildMember or request the full roster"
                    )
                return Permissions(0)
        else:
            raise TypeError("permissions_for requires a GuildMember or User")

        if guild.owner_id is None:
            raise RuntimeError("Guild owner snapshot is incomplete")
        if member.user.id == guild.owner_id:
            return Permissions((1 << 64) - 1)

        required_role_ids = {guild.id, *member.roles}
        missing_role_ids = {
            role_id for role_id in required_role_ids if guild.get_role(role_id) is None
        }
        if missing_role_ids:
            missing = ", ".join(str(role_id) for role_id in sorted(missing_role_ids))
            raise RuntimeError(f"Guild role snapshot is incomplete; missing: {missing}")

        return _effective_permissions(
            {"id": guild.id, "owner_id": guild.owner_id},
            {"roles": member.roles},
            [
                {"id": role.id, "permissions": role.permissions}
                for role_id in required_role_ids
                if (role := guild.get_role(role_id)) is not None
            ],
            member.user.id,
            {"permission_overwrites": self.permission_overwrites},
        )

    async def set_permissions(
        self,
        target: Role | GuildMember | User | int,
        *,
        overwrite: PermissionOverwrite | None | UnsetType = UNSET,
        type: PermissionOverwriteType | int | None = None,
        **permissions: bool | None,
    ) -> None:
        """Create, replace, or delete one guild-channel overwrite.

        Args:
            target: Role, member, user, or explicitly typed target ID.
            overwrite: Complete overwrite to write, or ``None`` to delete it.
            type: Target kind required for a bare integer ID.
            **permissions: Tri-state permission values used to build an overwrite.

        Raises:
            TypeError: Inputs are missing, mixed, or have unsupported types.
            RuntimeError: The channel lacks guild or HTTP context.
            ValueError: A permission or target value is invalid.
        """
        target_id, target_type = self._resolve_overwrite_target(target, type)
        if not isinstance(overwrite, UnsetType) and permissions:
            raise TypeError("Pass either overwrite or permission keywords, not both")
        if isinstance(overwrite, UnsetType):
            if not permissions:
                raise TypeError("Provide an overwrite, permission keywords, or None")
            resolved_overwrite: PermissionOverwrite | None = PermissionOverwrite(
                **permissions
            )
        elif overwrite is None:
            resolved_overwrite = None
        elif isinstance(overwrite, PermissionOverwrite):
            resolved_overwrite = overwrite
        else:
            raise TypeError("overwrite must be PermissionOverwrite or None")

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        if resolved_overwrite is None:
            await self._http.delete_channel_permissions(self.id, target_id)
            self.permission_overwrites = [
                item
                for item in self.permission_overwrites
                if int(item["id"]) != target_id
            ]
            return

        allow, deny = resolved_overwrite.pair()
        await self._http.edit_channel_permissions(
            self.id,
            target_id,
            allow=allow,
            deny=deny,
            type=int(target_type),
        )
        stored = ChannelPermissionOverwrite(
            id=target_id,
            type=target_type,
            allow=allow,
            deny=deny,
        ).to_dict()
        self.permission_overwrites = [
            item for item in self.permission_overwrites if int(item["id"]) != target_id
        ]
        self.permission_overwrites.append(stored)

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
        mention_author: bool | None = None,
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
            allowed_mentions: An ``AllowedMentions`` merged over the client's
                ``allowed_mentions``, or a raw allowed mentions dict.
            mention_author: Whether a reply notifies the replied-to author;
                overrides ``replied_user``.
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
            mention_author=mention_author,
            **combined_kwargs,
        )
        msg = _snapshot(Message.from_data, data, self._http)
        msg._channel = self
        msg._cache_guild(self.guild)
        return msg

    async def fetch_message(self, message_id: int | str) -> Message:
        """Fetch a message from this channel by ID.

        Args:
            message_id: The message ID to fetch.

        Returns:
            The fetched Message object.
        """
        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        data = await self._http.get_message(self.id, message_id)
        msg = _snapshot(Message.from_data, data, self._http)
        msg._channel = self
        msg._cache_guild(self.guild)
        return msg

    async def fetch_messages(self, limit: int = 50) -> list[Message]:
        """Fetch recent messages from this channel.

        Args:
            limit: The maximum number of messages to fetch (default 50).

        Returns:
            A list of Message objects.
        """
        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        data = await self._http.get_messages(self.id, limit=limit)
        msgs = [_snapshot(Message.from_data, msg_data, self._http) for msg_data in data]
        for msg in msgs:
            msg._channel = self
            msg._cache_guild(self.guild)
        return msgs

    def get_partial_message(self, message_id: int | str) -> PartialMessage:
        """Return a lightweight message handle for this channel.

        Args:
            message_id: Identity of the message used by this operation.

        Returns:
            The requested partial message.
        """
        return PartialMessage(
            channel_id=self.id,
            id=int(message_id),
            _http=self._http,
            _channel=self,
            _guild=self.guild,
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
            msg = _snapshot(Message.from_data, msg_data, self._http)
            msg._channel = self
            msg._cache_guild(self.guild)
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
        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        data = await self._http.get_pinned_messages(self.id, limit=limit, before=before)
        msgs = [
            _snapshot(Message.from_data, msg_data.get("message", msg_data), self._http)
            for msg_data in data["items"]
        ]
        for msg in msgs:
            msg._channel = self
            msg._guild = self.guild
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

    def _require_http(self) -> HTTPClient:
        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")
        return self._http

    def _require_thread(self, action: str) -> HTTPClient:
        if not self.is_thread:
            raise TypeError(f"Only threads can {action} (type={self.type})")
        return self._require_http()

    def _bind_thread(self, data: dict[str, Any], http: HTTPClient) -> Channel:
        thread = _snapshot(Channel.from_data, data, http)
        if thread.guild_id is None:
            thread.guild_id = self.guild_id
        thread._guild = self._guild
        member = data.get("member")
        if isinstance(member, dict):
            thread._me = self._own_thread_member(member, thread.id)
        return thread

    def _own_thread_member(
        self, data: dict[str, Any], thread_id: int
    ) -> ThreadMember | None:
        # Own memberships in thread lists may omit user_id; fill in the session
        # user, and skip the membership when that is unknown (unbound channel).
        user = self._state.user if self._state is not None else None
        if data.get("user_id") is None and user is None:
            return None
        return self._thread_member(
            data, thread_id, user_id=user.id if user is not None else None
        )

    def _thread_member(
        self, data: dict[str, Any], thread_id: int, *, user_id: int | None = None
    ) -> ThreadMember:
        member = ThreadMember.from_data(
            data,
            thread_id=thread_id,
            user_id=user_id,
            guild_id=self.guild_id,
            state=self._state,
        )
        guild_member = data.get("member")
        if isinstance(guild_member, dict) and isinstance(
            guild_member.get("user"), dict
        ):
            member._member = GuildMember.from_data(
                guild_member, self._http, guild_id=self.guild_id
            )
        return member

    async def edit(
        self,
        *,
        name: str | UnsetType = UNSET,
        topic: str | None | UnsetType = UNSET,
        nsfw: bool | UnsetType = UNSET,
        slowmode_delay: int | None | UnsetType = UNSET,
        default_auto_archive_duration: ThreadArchiveDuration | None | UnsetType = UNSET,
        default_thread_slowmode_delay: int | None | UnsetType = UNSET,
        archived: bool | UnsetType = UNSET,
        locked: bool | UnsetType = UNSET,
        invitable: bool | UnsetType = UNSET,
        auto_archive_duration: ThreadArchiveDuration | UnsetType = UNSET,
        reason: str | None = None,
    ) -> Channel:
        """Edit this channel or thread; only the arguments you pass are sent.

        Thread owners and moderators can rename, archive, lock and change
        ``auto_archive_duration`` or ``invitable``; any member can unarchive.
        Changing slowmode or unlocking needs a thread moderator.

        Args:
            name: New name, 1 to 100 characters for a thread.
            topic: New topic; None clears it.
            nsfw: Whether the channel is age restricted.
            slowmode_delay: Slowmode in seconds (0-21600); None sets 0 on a thread.
            default_auto_archive_duration: Stored default archive duration for
                threads in a text or announcement channel; None clears it.
            default_thread_slowmode_delay: Slowmode copied to new threads in this
                channel; None clears it.
            archived: Whether the thread is archived.
            locked: Whether only moderators can act in the thread.
            invitable: Whether non-moderators can add members to a private thread.
            auto_archive_duration: Minutes of inactivity before the thread archives.
            reason: Audit log reason.

        Returns:
            The updated channel.
        """
        http = self._require_http()
        payload: dict[str, Any] = {}
        if not isinstance(slowmode_delay, UnsetType):
            payload["rate_limit_per_user"] = slowmode_delay
        if not isinstance(default_auto_archive_duration, UnsetType):
            payload["default_auto_archive_duration"] = default_auto_archive_duration
        if not isinstance(default_thread_slowmode_delay, UnsetType):
            payload["default_thread_rate_limit_per_user"] = (
                default_thread_slowmode_delay
            )
        for key, value in (
            ("archived", archived),
            ("locked", locked),
            ("invitable", invitable),
            ("auto_archive_duration", auto_archive_duration),
        ):
            if not isinstance(value, UnsetType):
                payload[key] = value
        data = await http.modify_channel(
            self.id, name=name, topic=topic, nsfw=nsfw, reason=reason, **payload
        )
        channel = _snapshot(Channel.from_data, data, http)
        channel._guild = self._guild
        channel._me = self._me
        channel._thread_members = dict(self._thread_members)
        return channel

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this channel or thread.

        Args:
            reason: Audit log reason.

        Returns:
            None.
        """
        await self._require_http().delete_channel(self.id, reason=reason)

    async def create_thread(
        self,
        *,
        name: str,
        message: Any | None = None,
        auto_archive_duration: ThreadArchiveDuration | UnsetType = UNSET,
        type: ChannelType | int | None = None,
        reason: str | None = None,
        invitable: bool = True,
        slowmode_delay: int | None = None,
    ) -> Channel:
        """Start a thread in this text or announcement channel.

        With ``message``, the thread starts from that message and is public (an
        announcement thread in an announcement channel); ``type`` and
        ``invitable`` are ignored, as Fluxer does not accept them there.

        Args:
            name: Thread name, 1 to 100 characters.
            message: The message, or its ID, to start the thread from.
            auto_archive_duration: Minutes of inactivity before archiving. When
                omitted Fluxer uses 4320; it does not apply the channel's
                ``default_auto_archive_duration`` to new threads.
            type: Thread type for a thread without a message; defaults to
                ``ChannelType.PRIVATE_THREAD``.
            reason: Audit log reason.
            invitable: Whether non-moderators can add members to a private thread.
            slowmode_delay: Slowmode in seconds; defaults to the channel's.

        Returns:
            The created thread.
        """
        http = self._require_http()
        rate_limit: int | UnsetType = (
            UNSET if slowmode_delay is None else slowmode_delay
        )
        if message is not None:
            data = await http.start_thread_with_message(
                self.id,
                getattr(message, "id", message),
                name=name,
                auto_archive_duration=auto_archive_duration,
                rate_limit_per_user=rate_limit,
                reason=reason,
            )
        else:
            thread_type = ChannelType.PRIVATE_THREAD if type is None else type
            data = await http.start_thread_without_message(
                self.id,
                name=name,
                type=int(thread_type),
                auto_archive_duration=auto_archive_duration,
                invitable=invitable
                if thread_type == ChannelType.PRIVATE_THREAD
                else UNSET,
                rate_limit_per_user=rate_limit,
                reason=reason,
            )
        return self._bind_thread(data, http)

    async def archived_threads(
        self,
        *,
        private: bool = False,
        joined: bool = False,
        limit: int | None = 100,
        before: Any | datetime | None = None,
    ) -> AsyncIterator[Channel]:
        """Iterate over this channel's archived threads, newest first.

        Private archived threads need a thread moderator; ``joined=True`` lists
        only the private threads the current user is in.

        Args:
            private: Whether to list private instead of public threads.
            joined: Whether to list only joined private threads; needs ``private``.
            limit: Maximum threads to yield; None yields every thread.
            before: A datetime, or an object with an ``id`` such as a thread,
                bounding the results.

        Yields:
            Each archived thread.

        Raises:
            ValueError: ``joined`` was set without ``private``.
        """
        if joined and not private:
            raise ValueError("joined=True requires private=True")
        http = self._require_http()

        cursor: str | None = None
        if before is not None:
            if joined:
                cursor = str(
                    datetime_to_snowflake(before)
                    if isinstance(before, datetime)
                    else before.id
                )
            else:
                moment = (
                    before
                    if isinstance(before, datetime)
                    else snowflake_to_datetime(before.id)
                )
                cursor = moment.astimezone(timezone.utc).isoformat()

        if joined:
            endpoint = http.get_joined_private_archived_threads
        elif private:
            endpoint = http.get_private_archived_threads
        else:
            endpoint = http.get_public_archived_threads

        while limit is None or limit > 0:
            page = 100 if limit is None else max(2, min(100, limit))
            data = await endpoint(self.id, before=cursor, limit=page)
            threads = data.get("threads", [])
            members = {
                int(item["id"]): item
                for item in data.get("members", [])
                if item.get("id") is not None
            }
            for item in threads:
                thread = self._bind_thread(item, http)
                if thread.id in members:
                    thread._me = self._own_thread_member(members[thread.id], thread.id)
                yield thread
                if limit is not None:
                    limit -= 1
                    if limit <= 0:
                        return
            if not data.get("has_more") or not threads:
                return
            last = threads[-1]
            cursor = (
                str(last["id"])
                if joined
                else (last.get("thread_metadata") or {}).get("archive_timestamp")
            )
            if cursor is None:
                return

    async def join(self) -> None:
        """Join this thread.

        Returns:
            None.
        """
        await self._require_thread("be joined").join_thread(self.id)

    async def leave(self) -> None:
        """Leave this thread.

        Returns:
            None.
        """
        await self._require_thread("be left").leave_thread(self.id)

    async def add_user(self, user: Any, /) -> None:
        """Add a user to this thread.

        Needs ``SEND_MESSAGES_IN_THREADS``; in a private thread that is not
        invitable, you or the user must be a thread moderator.

        Args:
            user: The user, member or ID to add.

        Returns:
            None.
        """
        http = self._require_thread("have members added")
        await http.add_thread_member(self.id, getattr(user, "id", user))

    async def remove_user(self, user: Any, /) -> None:
        """Remove a user from this thread.

        Needs a thread moderator, or the owner of a private thread.

        Args:
            user: The user, member or ID to remove.

        Returns:
            None.
        """
        http = self._require_thread("have members removed")
        await http.remove_thread_member(self.id, getattr(user, "id", user))

    async def fetch_member(self, user_id: int, /) -> ThreadMember:
        """Fetch one member of this thread; bots only.

        Args:
            user_id: The member's user ID.

        Returns:
            The thread membership.
        """
        http = self._require_thread("fetch members")
        data = await http.get_thread_member(self.id, user_id)
        return self._thread_member(data, self.id)

    async def fetch_members(self) -> list[ThreadMember]:
        """Fetch every member of this thread; bots only.

        Returns:
            The thread memberships in ascending user ID order.
        """
        http = self._require_thread("fetch members")
        result: list[ThreadMember] = []
        after: int | None = None
        while True:
            page = await http.get_thread_members(self.id, after=after, limit=100)
            result.extend(self._thread_member(item, self.id) for item in page)
            if len(page) < 100:
                return result
            after = result[-1].id

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
