"""Central ownership of Fluxer Gateway entities and bounded cache indexes.

HTTP snapshots are parsed separately and never write through to live state.
"""

from __future__ import annotations

import asyncio

from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, fields
from functools import lru_cache
from time import monotonic
from typing import TYPE_CHECKING, Any, TypeVar
from weakref import WeakValueDictionary

from ._types import UNSET, UnsetType
from .audit_logs import AuditLogEntry
from .enums import ChannelType
from .events import fluxer_event_from_dispatch
from .invite import Invite
from .mentions import AllowedMentions
from .models import Channel, Guild, GuildMember, Message, User, VoiceState
from .models.role import Role
from .models.reaction import (
    RawReactionActionEvent,
    RawReactionClearEvent,
    RawReactionClearEmojiEvent,
)
from .models.thread import ThreadMember
from .raw_models import (
    RawBulkMessageDeleteEvent,
    RawMemberRemoveEvent,
    RawMessageDeleteEvent,
    RawMessageUpdateEvent,
    RawPresenceUpdateEvent,
    RawThreadDeleteEvent,
    RawThreadMembersUpdate,
    RawThreadUpdateEvent,
    RawTypingEvent,
)
from .utils import _try_parse_time as parse_time

if TYPE_CHECKING:
    from .http import HTTPClient

_Events = list[tuple[str, tuple[Any, ...]]]
_VoiceKey = tuple[int, int, str | None]
_T = TypeVar("_T")
_FORUM_TYPES = frozenset({ChannelType.GUILD_FORUM, ChannelType.GUILD_MEDIA})


@lru_cache(maxsize=None)
def _field_names(cls: type) -> tuple[str, ...]:
    return tuple(item.name for item in fields(cls) if not item.name.startswith("_"))


def _update(target: Any, source: Any, *, exclude: tuple[str, ...] = ()) -> Any:
    for name in _field_names(type(source)):
        if name not in exclude:
            setattr(target, name, getattr(source, name))
    return target


@lru_cache(maxsize=None)
def _slot_names(cls: type) -> tuple[str, ...]:
    names: list[str] = []
    for klass in cls.__mro__:
        slots = klass.__dict__.get("__slots__", ())
        for name in (slots,) if isinstance(slots, str) else slots:
            if not name.startswith("__") and name not in names:
                names.append(name)
    return tuple(names)


def _shallow_copy(obj: _T) -> _T:
    """Snapshot an entity for ``before`` arguments, like discord.py's copy.copy.

    Attributes are shared, not copied, and read-only collection views are kept
    as they are instead of going through the model's ``__setattr__``.
    """
    clone = object.__new__(type(obj))
    for name in _slot_names(type(obj)):
        try:
            object.__setattr__(clone, name, object.__getattribute__(obj, name))
        except AttributeError:
            pass
    instance_dict = getattr(obj, "__dict__", None)
    if instance_dict:
        object.__getattribute__(clone, "__dict__").update(instance_dict)
    return clone


def _user_key(user: User) -> tuple[Any, ...]:
    return (
        user.username,
        user.discriminator,
        user.global_name,
        user.avatar_hash,
        user.banner_hash,
        user.flags,
    )


# Guild fields whose name differs from the payload key they are parsed from.
_GUILD_PAYLOAD_KEYS = {
    "icon_hash": "icon",
    "banner_hash": "banner",
    "splash_hash": "splash",
    "embed_splash_hash": "embed_splash",
}


class _MemberView(Mapping[tuple[int, int], GuildMember]):
    """Compatibility lookup view without an additional member cache."""

    def __init__(self, state: ConnectionState) -> None:
        self._state = state

    def __getitem__(self, key: tuple[int, int]) -> GuildMember:
        member = self._state.get_member(*key)
        if member is None:
            raise KeyError(key)
        return member

    def __iter__(self) -> Iterator[tuple[int, int]]:
        for guild in self._state.guilds.values():
            for user_id in guild._members:
                yield guild.id, user_id

    def __len__(self) -> int:
        return sum(len(guild._members) for guild in self._state.guilds.values())


@dataclass(slots=True)
class _MemberRequest:
    nonce: str
    full: bool
    started: float = field(default_factory=monotonic)
    count: int | None = None
    chunks: dict[int, set[int]] = field(default_factory=dict)
    timer: asyncio.TimerHandle | None = field(default=None, repr=False)


@dataclass(slots=True)
class ConnectionState:
    """Own live entities, retention policies, and ordered event parsers.

    Attributes:
        http: Transport used by bound models.
        max_messages: Maximum messages; nonpositive values disable retention.
        cache_members: Whether guilds retain members between events.
        max_private_channels: Private-channel limit; None means unlimited.
        user: Current account, retained strongly until state is cleared.
        users: Weak identity map for referenced users.
        guilds: Live guilds indexed by ID.
        channels: Shared channel index.
        members: Read-only view over guild-owned memberships.
        messages: Bounded message index in retention order.
        voice_states: Voice connections indexed by guild and participant identity.
        allowed_mentions: Client-wide mention policy merged into every send.
    """

    http: HTTPClient | None = None
    max_messages: int = 1000
    cache_members: bool = True
    max_private_channels: int | None | UnsetType = UNSET
    allowed_mentions: AllowedMentions | None = None
    user: User | None = None
    users: WeakValueDictionary[int, User] = field(default_factory=WeakValueDictionary)
    guilds: dict[int, Guild] = field(default_factory=dict)
    channels: dict[int, Channel] = field(default_factory=dict)
    messages: OrderedDict[int, Message] = field(default_factory=OrderedDict)
    voice_states: dict[int, dict[tuple[int, str | None], VoiceState]] = field(
        default_factory=dict
    )
    _private_channels: OrderedDict[int, Channel] = field(default_factory=OrderedDict)
    _channel_messages: dict[int, set[int]] = field(default_factory=dict)
    _guild_messages: dict[int, set[int]] = field(default_factory=dict)
    _voice_channels: dict[int, dict[_VoiceKey, VoiceState]] = field(
        default_factory=dict
    )
    _voice_users: dict[tuple[int, int], dict[str | None, VoiceState]] = field(
        default_factory=dict
    )
    _voice_tombstones: OrderedDict[_VoiceKey, int | None] = field(
        default_factory=OrderedDict
    )
    _member_requests: dict[int, _MemberRequest] = field(default_factory=dict)
    _member_ranges: dict[int, tuple[int, list[list[int]]]] = field(default_factory=dict)
    _member_lists: dict[int, dict[int, int | dict[str, Any]]] = field(
        default_factory=dict
    )
    _parsers: dict[str, Callable[[dict[str, Any]], _Events]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate retention and register event-specific parsers."""
        if (
            not isinstance(self.max_private_channels, UnsetType)
            and self.max_private_channels is not None
        ):
            if (
                not isinstance(self.max_private_channels, int)
                or self.max_private_channels < 0
            ):
                raise ValueError("max_private_channels must be nonnegative or None")
        for name in dir(self):
            if name.startswith("_parse_") and name != "_parse_dispatch":
                self._parsers[name[7:].upper()] = getattr(self, name)

    @property
    def members(self) -> Mapping[tuple[int, int], GuildMember]:
        """Read memberships through the owning guilds.

        Returns:
            A view without an additional member cache.
        """
        return _MemberView(self)

    def clear(self) -> None:
        """Release entities and pending non-replayable request state.

        Transport and retention policies are preserved.
        """
        self._interrupt()
        self.user = None
        for cache in (
            self.users,
            self.guilds,
            self.channels,
            self.messages,
            self.voice_states,
            self._private_channels,
            self._channel_messages,
            self._guild_messages,
            self._voice_channels,
            self._voice_users,
            self._voice_tombstones,
        ):
            cache.clear()

    def _interrupt(self) -> None:
        for guild in self.guilds.values():
            guild._member_cache_complete = False
        for guild_id in tuple(self._member_requests):
            self._discard_member_request(guild_id)
        self._member_ranges.clear()
        self._member_lists.clear()

    def store_user(self, data: dict[str, Any]) -> User:
        """Hydrate a shared user without downgrading ID-only references.

        Args:
            data: Current-account, public-user, or ID-only payload.

        Returns:
            The shared live user.
        """
        user_id = int(data["id"])
        previous = self.users.get(user_id)
        if previous is not None:
            if len(data) == 1 or data == previous.raw_data:
                return previous
            merged = {**previous.raw_data, **data}
            if "username" in data:
                for key in ("bot", "system", "mention_flags"):
                    if key not in data:
                        merged.pop(key, None)
            return _update(previous, User.from_data(merged, self.http))
        user = User.from_data(data, self.http)
        self.users[user_id] = user
        return user

    def store_guild(self, guild: Guild) -> Guild:
        """Adopt a parsed guild and its supplied entity collections.

        Args:
            guild: Parsed guild snapshot.

        Returns:
            The canonical live guild.
        """
        previous = self.guilds.get(guild.id)
        if previous is not None and previous is not guild:
            incoming = guild
            guild = _update(
                previous,
                incoming,
                exclude=(
                    "roles",
                    "channels",
                    "members",
                    "emojis",
                    "stickers",
                    "threads",
                ),
            )
            for name in ("roles", "emojis", "stickers"):
                target = getattr(guild, "_" + name)
                replacement = {
                    item.id: _update(target[item.id], item)
                    if item.id in target
                    else item
                    for item in getattr(incoming, name)
                }
                target.clear()
                target.update(replacement)
            channels = list(incoming.channels)
            members = list(incoming.members)
            for channel_id in set(guild._channels) - {
                channel.id for channel in channels
            }:
                self._remove_channel(channel_id)
            for member_id in set(guild._members) - {member.id for member in members}:
                guild._members.pop(member_id)
        else:
            channels = list(guild.channels)
            members = list(guild.members)
        self.guilds[guild.id] = guild
        guild._state = self
        for channel in channels:
            channel.guild_id = guild.id
            self.store_channel(channel)
        if not self.cache_members:
            guild._members.clear()
        for member in members:
            member.guild_id = guild.id
            self.store_member(member)
        guild._member_cache_complete = False
        return guild

    def _intern_user(self, user: User) -> User:
        if user.raw_data:
            return self.store_user(user.raw_data)
        previous = self.users.get(user.id)
        if previous is not None:
            return _update(previous, user) if user.username else previous
        self.users[user.id] = user
        return user

    def get_channel(self, channel_id: int) -> Channel | None:
        """Look up a channel and refresh private-channel recency.

        Args:
            channel_id: Channel to retrieve.

        Returns:
            The cached channel, when present.
        """
        channel = self.channels.get(channel_id)
        if channel_id in self._private_channels:
            self._private_channels.move_to_end(channel_id)
        return channel

    def store_channel(self, channel: Channel) -> Channel:
        """Adopt a channel while preserving the live object's identity.

        Args:
            channel: Complete parsed channel.

        Returns:
            The channel, whether or not retention is enabled.
        """
        channel.recipients = [self._intern_user(u) for u in channel.recipients]
        previous = self.channels.get(channel.id)
        if previous is not None and previous is not channel:
            channel = _update(previous, channel)
        channel._state = self
        channel._guild = None
        self.channels[channel.id] = channel
        if channel.guild_id is not None:
            guild = self.guilds.get(channel.guild_id)
            if guild is not None:
                if channel.is_thread:
                    guild._threads[channel.id] = channel
                else:
                    guild._channels[channel.id] = channel
        else:
            self._private_channels[channel.id] = channel
            self._private_channels.move_to_end(channel.id)
            bound = self.max_private_channels
            if isinstance(bound, UnsetType):
                bound = 128 if self.user is None or self.user.bot else None
            if bound is not None:
                while len(self._private_channels) > bound:
                    channel_id, _ = self._private_channels.popitem(last=False)
                    self.channels.pop(channel_id, None)
        return channel

    def store_member(self, member: GuildMember) -> GuildMember:
        """Retain a hydrated member only in its guild's member map.

        Args:
            member: Parsed membership.

        Returns:
            The canonical member when retention is enabled.
        """
        member.user = self._intern_user(member.user)
        guild = (
            self.guilds.get(member.guild_id) if member.guild_id is not None else None
        )
        if self.cache_members and guild is not None:
            previous = guild._members.get(member.id)
            if previous is not None and previous is not member:
                member = _update(previous, member)
            guild._members[member.id] = member
        return member

    def get_member(self, guild_id: int | None, user_id: int) -> GuildMember | None:
        """Look up a member through its owning guild.

        Args:
            guild_id: Guild to search.
            user_id: Account to retrieve.

        Returns:
            The retained member, when available.
        """
        guild = self.guilds.get(guild_id) if guild_id is not None else None
        return guild.get_member(user_id) if guild is not None else None

    def _hydrate_message(self, message: Message) -> None:
        message._guild_id = message.guild_id
        message._state = self
        message._guild = None
        message._channel = None
        if message._member_from_cache:
            # Parsing attached a snapshot copy of the cached member; live
            # messages share the cached member itself instead.
            message.member = None
            message._member_from_cache = False
        author = message.author
        account = self._intern_user(
            author.user if isinstance(author, GuildMember) else author
        )
        message.mentions = [self._intern_user(u) for u in message.mentions]
        message.users = [self._intern_user(u) for u in message.users]
        channel = self.channels.get(message.channel_id)
        if message._guild_id is None and channel is not None:
            message._guild_id = channel.guild_id
        if message.member is not None:
            message.member.guild_id = message.guild_id
            message.member.user = account
            message.member = self.store_member(message.member)
            message.author = message.member
        else:
            message.author = account
            message._resolve_author(live=True)
        if isinstance(message.referenced_message, Message):
            message.referenced_message._guild_id = message.guild_id
            self._hydrate_message(message.referenced_message)

    def store_message(self, message: Message) -> Message:
        """Adopt a message into the bounded cache and entity indexes.

        Args:
            message: Parsed live message.

        Returns:
            The canonical message, including when caching is disabled.
        """
        self._hydrate_message(message)
        previous = self.remove_message(message.id)
        if previous is not None and previous is not message:
            guild_id = message._guild_id
            message = _update(previous, message)
            message._guild_id = guild_id
            for reaction in message.reactions:
                reaction._message = message
        if self.max_messages > 0:
            self.messages[message.id] = message
            self._channel_messages.setdefault(message.channel_id, set()).add(message.id)
            if message.guild_id is not None:
                self._guild_messages.setdefault(message.guild_id, set()).add(message.id)
            while len(self.messages) > self.max_messages:
                self.remove_message(next(iter(self.messages)))
        return message

    def get_message(self, message_id: int | str | None) -> Message | None:
        """Look up a retained message without fetching it.

        Args:
            message_id: Message ID, or None.

        Returns:
            The cached message, when available.
        """
        try:
            return (
                self.messages.get(int(message_id)) if message_id is not None else None
            )
        except (TypeError, ValueError):
            return None

    def remove_message(self, message_id: int | str | None) -> Message | None:
        """Remove a message and its secondary index entries.

        Args:
            message_id: Message ID, or None.

        Returns:
            The removed message, when present.
        """
        try:
            message = (
                self.messages.pop(int(message_id), None)
                if message_id is not None
                else None
            )
        except (TypeError, ValueError):
            return None
        if message is not None:
            for index, key in (
                (self._channel_messages, message.channel_id),
                (self._guild_messages, message.guild_id),
            ):
                if key is not None and key in index:
                    index[key].discard(message.id)
                    if not index[key]:
                        del index[key]
        return message

    def _remove_channel(self, channel_id: int) -> Channel | None:
        channel = self.channels.pop(channel_id, None)
        self._private_channels.pop(channel_id, None)
        if (
            channel is not None
            and channel.guild_id is not None
            and channel.guild_id in self.guilds
        ):
            self.guilds[channel.guild_id]._channels.pop(channel_id, None)
            self.guilds[channel.guild_id]._threads.pop(channel_id, None)
        for message_id in tuple(self._channel_messages.get(channel_id, ())):
            self.remove_message(message_id)
        for key, voice in tuple(self._voice_channels.get(channel_id, {}).items()):
            self._remove_voice(key, voice)
        if channel is not None and channel.guild_id is not None:
            subscription = self._member_ranges.get(channel.guild_id)
            if subscription is not None and subscription[0] == channel_id:
                self._member_ranges.pop(channel.guild_id, None)
                self._member_lists.pop(channel.guild_id, None)
        return channel

    def _store_thread(self, data: dict[str, Any], guild_id: int | None) -> Channel:
        payload = dict(data)
        if guild_id is not None and not payload.get("guild_id"):
            payload["guild_id"] = str(guild_id)
        thread = self.store_channel(Channel.from_data(payload, self.http))
        member = data.get("member")
        if isinstance(member, dict) and self.user is not None:
            thread._me = ThreadMember.from_data(
                member,
                thread_id=thread.id,
                user_id=self.user.id,
                guild_id=thread.guild_id,
                state=self,
            )
        return thread

    def _uncache_thread(self, thread_id: int) -> Channel | None:
        """Drop a thread that still exists, keeping its cached messages.

        Matches discord.py's ``Guild._remove_thread``. Deleted threads go through
        ``_remove_channel`` instead, which also purges their messages.
        """
        thread = self.channels.pop(thread_id, None)
        guild_id = thread.guild_id if thread is not None else None
        if guild_id is not None and guild_id in self.guilds:
            self.guilds[guild_id]._threads.pop(thread_id, None)
        return thread

    def _remove_threads_by_parent(self, guild: Guild, parent_id: int) -> list[Channel]:
        removed = []
        for thread in tuple(guild._threads.values()):
            if thread.parent_id == parent_id:
                self._remove_channel(thread.id)
                removed.append(thread)
        return removed

    def _remove_voice(self, key: _VoiceKey, voice: VoiceState) -> None:
        guild_id, user_id, connection_id = key
        self.voice_states.get(guild_id, {}).pop((user_id, connection_id), None)
        if not self.voice_states.get(guild_id):
            self.voice_states.pop(guild_id, None)
        if voice.channel_id is not None:
            by_channel = self._voice_channels.get(voice.channel_id, {})
            by_channel.pop(key, None)
            if not by_channel:
                self._voice_channels.pop(voice.channel_id, None)
        by_user = self._voice_users.get((guild_id, user_id), {})
        by_user.pop(connection_id, None)
        if not by_user:
            self._voice_users.pop((guild_id, user_id), None)

    def _store_voice_state(self, data: dict[str, Any]) -> VoiceState:
        return self._apply_voice_state(data)[0]

    def _apply_voice_state(self, data: dict[str, Any]) -> tuple[VoiceState, bool]:
        voice = VoiceState.from_data(data, self.http)
        if voice.guild_id is None or voice.user_id is None:
            return voice, True
        key = (voice.guild_id, voice.user_id, voice.connection_id)
        previous = self.voice_states.get(voice.guild_id, {}).get(
            (voice.user_id, voice.connection_id)
        )
        version = (
            previous.version
            if previous is not None
            else self._voice_tombstones.get(key)
        )
        if (
            version is not None
            and voice.version is not None
            and (
                voice.version < version
                or (previous is None and voice.version == version)
            )
        ):
            if previous is not None:
                return previous, False
            voice.channel_id = None
            voice.version = version
            return voice, False
        if previous is not None:
            self._remove_voice(key, previous)
            voice = _update(previous, voice)
        if voice.channel_id is None:
            self._remember_voice_departure(key, voice.version)
        else:
            self._voice_tombstones.pop(key, None)
            self.voice_states.setdefault(key[0], {})[(key[1], key[2])] = voice
            self._voice_channels.setdefault(voice.channel_id, {})[key] = voice
            self._voice_users.setdefault((key[0], key[1]), {})[key[2]] = voice
        if voice.member is not None:
            voice.member.guild_id = voice.guild_id
            voice.member = self.store_member(voice.member)
        return voice, True

    def _remember_voice_departure(self, key: _VoiceKey, version: int | None) -> None:
        self._voice_tombstones[key] = version
        self._voice_tombstones.move_to_end(key)
        while len(self._voice_tombstones) > 2048:
            self._voice_tombstones.popitem(last=False)

    def _clear_guild_voice(self, guild_id: int) -> None:
        for (user_id, connection_id), voice in tuple(
            self.voice_states.get(guild_id, {}).items()
        ):
            self._remove_voice((guild_id, user_id, connection_id), voice)
        self._clear_voice_tombstones(guild_id)

    def _clear_voice_tombstones(self, guild_id: int) -> None:
        for key in tuple(self._voice_tombstones):
            if key[0] == guild_id:
                del self._voice_tombstones[key]

    def _guild_snapshot(self, data: dict[str, Any]) -> Guild:
        data = {**data.get("properties", {}), **data}
        parsed = Guild.from_data(data, self.http)
        guild = self.guilds.get(parsed.id)
        if guild is None:
            guild = Guild(id=parsed.id, _http=self.http)
            guild._state = self
            self.guilds[guild.id] = guild
        collections = ("roles", "channels", "members", "emojis", "stickers", "threads")
        for name in _field_names(Guild):
            if _GUILD_PAYLOAD_KEYS.get(name, name) in data and name not in collections:
                setattr(guild, name, getattr(parsed, name))
        for name in ("roles", "emojis", "stickers"):
            if name in data:
                target = getattr(guild, "_" + name)
                incoming = {item.id: item for item in getattr(parsed, name)}
                for item_id in tuple(target):
                    if item_id not in incoming:
                        del target[item_id]
                for item_id, item in incoming.items():
                    target[item_id] = (
                        _update(target[item_id], item) if item_id in target else item
                    )
        if "channels" in data:
            channel_ids = {c.id for c in parsed.channels}
            for channel_id in tuple(guild._channels):
                if channel_id not in channel_ids:
                    self._remove_channel(channel_id)
            for channel in parsed.channels:
                self.store_channel(channel)
        if "threads" in data:
            incoming_threads = {int(item["id"]) for item in data["threads"]}
            for thread_id in tuple(guild._threads):
                if thread_id not in incoming_threads:
                    self._uncache_thread(thread_id)
            for item in data["threads"]:
                self._store_thread(item, guild.id)
        if "members" in data:
            self._discard_member_request(guild.id)
            member_ids = {m.id for m in parsed.members} if self.cache_members else set()
            for user_id in tuple(guild._members):
                if user_id not in member_ids:
                    del guild._members[user_id]
            for member in parsed.members:
                self.store_member(member)
            guild._member_cache_complete = False
        if "voice_states" in data:
            voices = data["voice_states"]
            identities = {
                (int(voice["user_id"]), voice.get("connection_id"))
                for voice in voices
                if voice.get("user_id") is not None
            }
            for identity, previous in tuple(
                self.voice_states.get(guild.id, {}).items()
            ):
                if identity not in identities:
                    key = (guild.id, *identity)
                    self._remove_voice(key, previous)
                    self._remember_voice_departure(key, previous.version)
            for voice in voices:
                self._store_voice_state({**voice, "guild_id": str(guild.id)})
        return guild

    def _parse_dispatch(self, name: str, data: Any) -> _Events:
        parser = self._parsers.get(name)
        return (
            parser(data)
            if parser is not None and isinstance(data, dict)
            else self._fallback(name, data)
        )

    def _fallback(self, name: str, data: Any) -> _Events:
        return [
            (f"on_{name.lower()}", (data,)),
            ("on_fluxer_event", (fluxer_event_from_dispatch(name, data),)),
        ]

    def _raw(self, name: str, data: Any) -> _Events:
        """Only the ``on_fluxer_event`` entry, for events whose ``on_<name>`` is modeled."""
        return [("on_fluxer_event", (fluxer_event_from_dispatch(name, data),))]

    def _track_user(self, user_id: int) -> tuple[User | None, tuple[Any, ...] | None]:
        user = self.users.get(user_id)
        if user is None:
            return None, None
        return _shallow_copy(user), _user_key(user)

    def _user_changed(
        self, before: User | None, key: tuple[Any, ...] | None, user_id: int
    ) -> _Events:
        after = self.users.get(user_id)
        if before is None or after is None or _user_key(after) == key:
            return []
        return [("on_user_update", (before, after))]

    # -- Session -------------------------------------------------------------

    def _parse_ready(self, data: dict[str, Any]) -> _Events:
        self.clear()
        users = [self.store_user(item) for item in data.get("users", [])]
        self.user = self.store_user(data["user"])
        if self.http is not None:
            self.http._user_id = self.user.id
        for guild in data.get("guilds", []):
            self._guild_snapshot(guild)
        for channel in data.get("private_channels", []):
            self.store_channel(Channel.from_data(channel, self.http))
        del users
        return [("on_ready", ())]

    def _parse_resumed(self, data: dict[str, Any]) -> _Events:
        return [("on_resumed", ())]

    def _parse_user_update(self, data: dict[str, Any]) -> _Events:
        user_id = int(data["id"])
        before, key = self._track_user(user_id)
        self.user = self.store_user(data)
        return self._user_changed(before, key, user_id) + self._raw("USER_UPDATE", data)

    # -- Guilds --------------------------------------------------------------

    def _parse_guild_create(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["id"])
        if data.get("unavailable") is True:
            self._guild_snapshot(data)
            return []
        known = guild_id in self.guilds
        guild = self._guild_snapshot(
            {"unavailable": False, "unavailable_hidden": False, **data}
        )
        if "unavailable" in data:
            # A bot's post-Ready burst and recoveries say unavailable: false.
            available = True
        elif self.user is not None and self.user.bot:
            # A bot's first Guild Create for a guild joined mid-session has no
            # unavailable field, even after an earlier unavailable Guild Delete.
            available = False
        else:
            # User sessions never receive the field; a known guild recovered.
            available = known
        return [("on_guild_available" if available else "on_guild_join", (guild,))]

    def _parse_guild_sync(self, data: dict[str, Any]) -> _Events:
        self._guild_snapshot(
            {"unavailable": False, "unavailable_hidden": False, **data}
        )
        return self._fallback("GUILD_SYNC", data)

    def _parse_guild_update(self, data: dict[str, Any]) -> _Events:
        previous = self.guilds.get(int(data.get("id") or data["guild_id"]))
        before = _shallow_copy(previous) if previous is not None else None
        was_unavailable = previous is not None and previous.unavailable
        guild = self._guild_snapshot(data)
        if "features" in data and "unavailable" not in data:
            guild.unavailable = bool(
                {
                    "UNAVAILABLE_FOR_EVERYONE",
                    "UNAVAILABLE_FOR_EVERYONE_BUT_STAFF",
                }.intersection(guild.features)
            )
        if guild.unavailable:
            guild._member_cache_complete = False
            self._discard_member_request(guild.id)
        events: _Events = []
        if before is not None:
            events.append(("on_guild_update", (before, guild)))
            if guild.unavailable and not was_unavailable:
                events.append(("on_guild_unavailable", (guild,)))
        return events + self._raw("GUILD_UPDATE", data)

    def _parse_guild_delete(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["id"])
        guild = self.guilds.get(guild_id)
        events: _Events = []
        if data.get("unavailable", False):
            was_available = guild is not None and not guild.unavailable
            guild = self._guild_snapshot(data)
            guild._member_cache_complete = False
            if was_available:
                events.append(("on_guild_unavailable", (guild,)))
        else:
            if guild is not None:
                for channel_id in tuple(guild._channels):
                    self._remove_channel(channel_id)
                for thread_id in tuple(guild._threads):
                    self._remove_channel(thread_id)
            for message_id in tuple(self._guild_messages.get(guild_id, ())):
                self.remove_message(message_id)
            self._clear_guild_voice(guild_id)
            self.guilds.pop(guild_id, None)
            if guild is not None:
                events.append(("on_guild_remove", (guild,)))
        self._discard_member_request(guild_id)
        self._member_ranges.pop(guild_id, None)
        self._member_lists.pop(guild_id, None)
        return events

    def _parse_guild_counts_update(self, data: dict[str, Any]) -> _Events:
        for item in data.get("counts", []):
            guild = self.guilds.get(int(item["guild_id"]))
            if guild is not None:
                guild.member_count = item["member_count"]
                guild.online_count = item["online_count"]
                if (
                    guild.member_cache_complete
                    and len(guild.members) != guild.member_count
                ):
                    guild._member_cache_complete = False
        return self._fallback("GUILD_COUNTS_UPDATE", data)

    def _parse_guild_audit_log_entry_create(self, data: dict[str, Any]) -> _Events:
        events: _Events = []
        if data.get("guild_id") and int(data["guild_id"]) in self.guilds:
            events.append(
                ("on_audit_log_entry_create", (AuditLogEntry.from_data(data),))
            )
        return events + self._fallback("GUILD_AUDIT_LOG_ENTRY_CREATE", data)

    def _parse_guild_emojis_update(self, data: dict[str, Any]) -> _Events:
        guild = self.guilds.get(int(data["guild_id"]))
        before = [_shallow_copy(item) for item in guild.emojis] if guild else []
        self._guild_snapshot({"id": data["guild_id"], "emojis": data.get("emojis", [])})
        events: _Events = []
        if guild is not None:
            events.append(
                ("on_guild_emojis_update", (guild, before, list(guild.emojis)))
            )
        return events + self._raw("GUILD_EMOJIS_UPDATE", data)

    def _parse_guild_stickers_update(self, data: dict[str, Any]) -> _Events:
        guild = self.guilds.get(int(data["guild_id"]))
        before = [_shallow_copy(item) for item in guild.stickers] if guild else []
        self._guild_snapshot(
            {"id": data["guild_id"], "stickers": data.get("stickers", [])}
        )
        events: _Events = []
        if guild is not None:
            events.append(
                ("on_guild_stickers_update", (guild, before, list(guild.stickers)))
            )
        return events + self._raw("GUILD_STICKERS_UPDATE", data)

    # -- Roles ---------------------------------------------------------------

    def _role_update(
        self, data: dict[str, Any], roles: list[dict[str, Any]]
    ) -> list[tuple[Role | None, Role]]:
        guild = self.guilds.get(int(data["guild_id"]))
        changes: list[tuple[Role | None, Role]] = []
        if guild is not None:
            for payload in roles:
                role = Role.from_data(payload, self.http, guild.id)
                previous = guild._roles.get(role.id)
                before = _shallow_copy(previous) if previous is not None else None
                guild._roles[role.id] = (
                    _update(previous, role) if previous is not None else role
                )
                changes.append((before, guild._roles[role.id]))
        return changes

    def _parse_guild_role_create(self, data: dict[str, Any]) -> _Events:
        events: _Events = [
            ("on_guild_role_create", (role,))
            for _, role in self._role_update(data, [data["role"]])
        ]
        return events + self._raw("GUILD_ROLE_CREATE", data)

    def _parse_guild_role_update(self, data: dict[str, Any]) -> _Events:
        events: _Events = [
            ("on_guild_role_update", (before, after))
            for before, after in self._role_update(data, [data["role"]])
            if before is not None
        ]
        return events + self._raw("GUILD_ROLE_UPDATE", data)

    def _parse_guild_role_update_bulk(self, data: dict[str, Any]) -> _Events:
        events: _Events = [
            ("on_guild_role_update", (before, after))
            for before, after in self._role_update(data, data.get("roles", []))
            if before is not None
        ]
        return events + self._raw("GUILD_ROLE_UPDATE_BULK", data)

    def _parse_guild_role_delete(self, data: dict[str, Any]) -> _Events:
        guild = self.guilds.get(int(data["guild_id"]))
        events: _Events = []
        if guild is not None:
            role_id = int(data["role_id"])
            role = guild._roles.pop(role_id, None)
            for member in guild.members:
                if role_id in member.roles:
                    member.roles.remove(role_id)
            if role is not None:
                events.append(("on_guild_role_delete", (role,)))
        return events + self._raw("GUILD_ROLE_DELETE", data)

    # -- Channels ------------------------------------------------------------

    def _guild_channel_events(self, channel: Channel) -> bool:
        return (
            channel.guild_id is not None
            and channel.guild_id in self.guilds
            and not channel.is_thread
        )

    def _parse_channel_create(self, data: dict[str, Any]) -> _Events:
        channel = self.store_channel(Channel.from_data(data, self.http))
        events: _Events = []
        if self._guild_channel_events(channel):
            events.append(("on_guild_channel_create", (channel,)))
        events.append(("on_channel_create", (channel,)))
        return events

    def _channel_update(self, data: dict[str, Any]) -> tuple[Channel, _Events]:
        previous = self.channels.get(int(data["id"]))
        before = _shallow_copy(previous) if previous is not None else None
        channel = self.store_channel(Channel.from_data(data, self.http))
        if before is None:
            return channel, []
        if channel.type == ChannelType.GROUP_DM:
            return channel, [("on_private_channel_update", (before, channel))]
        if self._guild_channel_events(channel):
            return channel, [("on_guild_channel_update", (before, channel))]
        return channel, []

    def _parse_channel_update(self, data: dict[str, Any]) -> _Events:
        channel, events = self._channel_update(data)
        return events + [("on_channel_update", (channel,))]

    def _parse_channel_update_bulk(self, data: dict[str, Any]) -> _Events:
        events: _Events = []
        for channel in data.get("channels", []):
            events.extend(
                self._channel_update({"guild_id": data.get("guild_id"), **channel})[1]
            )
        return events + self._raw("CHANNEL_UPDATE_BULK", data)

    def _parse_channel_delete(self, data: dict[str, Any]) -> _Events:
        channel_id = int(data["id"])
        guild = self.guilds.get(int(data["guild_id"])) if data.get("guild_id") else None
        channel = self._remove_channel(channel_id)
        if guild is None and channel is not None and channel.guild_id is not None:
            guild = self.guilds.get(channel.guild_id)
        events: _Events = []
        if guild is not None:
            if channel is not None and not channel.is_thread:
                events.append(("on_guild_channel_delete", (channel,)))
            # Fluxer deletes a channel's threads without a Thread Delete each.
            for thread in self._remove_threads_by_parent(guild, channel_id):
                events.append(("on_thread_delete", (thread,)))
                events.append(
                    (
                        "on_raw_thread_delete",
                        (RawThreadDeleteEvent._from_thread(thread),),
                    )
                )
        events.append(("on_channel_delete", (channel or data,)))
        return events

    def _parse_channel_pins_update(self, data: dict[str, Any]) -> _Events:
        channel = self.channels.get(int(data["channel_id"]))
        events: _Events = []
        if channel is not None:
            channel.last_pin_timestamp = data.get("last_pin_timestamp")
            last_pin = parse_time(data.get("last_pin_timestamp"))
            name = (
                "on_private_channel_pins_update"
                if channel.guild_id is None
                else "on_guild_channel_pins_update"
            )
            events.append((name, (channel, last_pin)))
        return events + self._fallback("CHANNEL_PINS_UPDATE", data)

    def _recipient(self, data: dict[str, Any], *, remove: bool) -> None:
        channel = self.channels.get(int(data["channel_id"]))
        if channel is not None:
            user = self.store_user(data["user"])
            channel.recipients = [u for u in channel.recipients if u.id != user.id]
            if not remove:
                channel.recipients.append(user)

    def _parse_channel_recipient_add(self, data: dict[str, Any]) -> _Events:
        self._recipient(data, remove=False)
        return self._fallback("CHANNEL_RECIPIENT_ADD", data)

    def _parse_channel_recipient_remove(self, data: dict[str, Any]) -> _Events:
        self._recipient(data, remove=True)
        return self._fallback("CHANNEL_RECIPIENT_REMOVE", data)

    def _parse_webhooks_update(self, data: dict[str, Any]) -> _Events:
        channel = (
            self.channels.get(int(data["channel_id"]))
            if data.get("channel_id")
            else None
        )
        events: _Events = []
        if channel is not None:
            events.append(("on_webhooks_update", (channel,)))
        return events + self._raw("WEBHOOKS_UPDATE", data)

    def _parse_invite_create(self, data: dict[str, Any]) -> _Events:
        invite = Invite.from_data(data, self.http)
        return [("on_invite_create", (invite,))] + self._raw("INVITE_CREATE", data)

    def _parse_invite_delete(self, data: dict[str, Any]) -> _Events:
        invite = Invite.from_data(data, self.http)
        return [("on_invite_delete", (invite,))] + self._raw("INVITE_DELETE", data)

    def _parse_passive_updates(self, data: dict[str, Any]) -> _Events:
        for channel_id, message_id in data.get("channels", {}).items():
            channel = self.channels.get(int(channel_id))
            if channel is not None:
                channel.last_message_id = (
                    int(message_id) if message_id is not None else None
                )
        for voice in data.get("voice_states", []):
            self._store_voice_state({"guild_id": data["guild_id"], **voice})
        return self._fallback("PASSIVE_UPDATES", data)

    # -- Threads -------------------------------------------------------------

    def _parse_thread_create(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        guild = self.guilds.get(guild_id)
        if guild is None:
            return self._raw("THREAD_CREATE", data)
        cached = guild._threads.get(int(data["id"]))
        was_member = cached is not None and cached._me is not None
        thread = self._store_thread(data, guild_id)
        events: _Events = []
        if cached is None and data.get("newly_created"):
            parent = thread.parent
            if parent is not None and parent.type in _FORUM_TYPES:
                parent.last_message_id = thread.id
            events.append(("on_thread_create", (thread,)))
            # The creator is a member, which discord.py reports as a join too.
            if thread._me is not None:
                events.append(("on_thread_join", (thread,)))
        elif cached is None or (thread._me is not None and not was_member):
            # Gained access to an existing thread, or joined a cached one.
            events.append(("on_thread_join", (thread,)))
        return events + self._raw("THREAD_CREATE", data)

    def _parse_thread_update(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        guild = self.guilds.get(guild_id)
        if guild is None:
            return self._raw("THREAD_UPDATE", data)
        raw = RawThreadUpdateEvent(data)
        cached = guild._threads.get(raw.thread_id)
        before = _shallow_copy(cached) if cached is not None else None
        thread = self._store_thread(data, guild_id)
        raw.thread = thread if cached is not None else None
        events: _Events = [("on_raw_thread_update", (raw,))]
        if thread.archived:
            # discord.py keeps only active threads cached.
            self._uncache_thread(thread.id)
        if before is not None:
            events.append(("on_thread_update", (before, thread)))
        else:
            events.append(("on_thread_join", (thread,)))
        return events + self._raw("THREAD_UPDATE", data)

    def _parse_thread_delete(self, data: dict[str, Any]) -> _Events:
        raw = RawThreadDeleteEvent(data)
        guild = self.guilds.get(raw.guild_id) if raw.guild_id is not None else None
        cached = guild._threads.get(raw.thread_id) if guild is not None else None
        raw.thread = cached
        events: _Events = [("on_raw_thread_delete", (raw,))]
        if cached is not None:
            self._remove_channel(cached.id)
            events.append(("on_thread_delete", (cached,)))
        return events + self._raw("THREAD_DELETE", data)

    def _parse_thread_list_sync(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        guild = self.guilds.get(guild_id)
        if guild is None:
            return self._fallback("THREAD_LIST_SYNC", data)
        if data.get("channel_ids") is None:
            previous = dict(guild._threads)
        else:
            parents = {int(item) for item in data["channel_ids"]}
            previous = {
                thread_id: thread
                for thread_id, thread in guild._threads.items()
                if thread.parent_id in parents
            }
        threads = {}
        for item in data.get("threads", []):
            thread = self._store_thread(item, guild_id)
            threads[thread.id] = thread
        for member in data.get("members", []):
            thread = threads.get(int(member["id"])) if member.get("id") else None
            if thread is not None and self.user is not None:
                thread._me = ThreadMember.from_data(
                    member,
                    thread_id=thread.id,
                    user_id=self.user.id,
                    guild_id=guild_id,
                    state=self,
                )
        events: _Events = [
            ("on_thread_join", (thread,))
            for thread_id, thread in threads.items()
            if thread_id not in previous
        ]
        for thread_id, thread in previous.items():
            if thread_id not in threads:
                self._uncache_thread(thread_id)
                events.append(("on_thread_remove", (thread,)))
        return events + self._fallback("THREAD_LIST_SYNC", data)

    def _parse_thread_member_update(self, data: dict[str, Any]) -> _Events:
        thread = self.channels.get(int(data["id"])) if data.get("id") else None
        if thread is not None and self.user is not None:
            thread._me = ThreadMember.from_data(
                data, user_id=self.user.id, guild_id=thread.guild_id, state=self
            )
        return self._fallback("THREAD_MEMBER_UPDATE", data)

    def _parse_thread_members_update(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        guild = self.guilds.get(guild_id)
        thread = guild._threads.get(int(data["id"])) if guild is not None else None
        if thread is None:
            return self._fallback("THREAD_MEMBERS_UPDATE", data)
        if data.get("member_count") is not None:
            thread.member_count = data["member_count"]
        raw = RawThreadMembersUpdate(data)
        self_id = self.user.id if self.user is not None else None
        events: _Events = []
        for item in data.get("added_members", []):
            member = ThreadMember.from_data(
                item, thread_id=thread.id, guild_id=guild_id, state=self
            )
            guild_member = item.get("member")
            if isinstance(guild_member, dict):
                member._member = self._member(
                    {
                        **guild_member,
                        "user": guild_member.get("user") or {"id": str(member.id)},
                    },
                    guild_id,
                )
                presence = item.get("presence")
                if isinstance(presence, dict):
                    member._member._presence_update(
                        RawPresenceUpdateEvent(presence, guild_id=guild_id)
                    )
            if member.id == self_id:
                # Thread Create arrives first with `member` and reports the join.
                joined = thread._me is None
                thread._me = member
                if joined:
                    events.append(("on_thread_join", (thread,)))
            else:
                thread._thread_members[member.id] = member
                events.append(("on_thread_member_join", (member,)))
        for value in data.get("removed_member_ids", []):
            user_id = int(value)
            if user_id == self_id:
                thread._me = None
                events.append(("on_thread_remove", (thread,)))
                continue
            removed = thread._thread_members.pop(user_id, None)
            events.append(("on_raw_thread_member_remove", (raw,)))
            if removed is not None:
                events.append(("on_thread_member_remove", (removed,)))
        return events + self._fallback("THREAD_MEMBERS_UPDATE", data)

    # -- Members -------------------------------------------------------------

    def _member(self, data: dict[str, Any], guild_id: int) -> GuildMember:
        return self.store_member(
            GuildMember.from_data(data, self.http, guild_id=guild_id)
        )

    def _parse_guild_member_add(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        member = self._member(data, guild_id)
        guild = self.guilds.get(guild_id)
        if guild is not None and guild.member_count is not None:
            guild.member_count += 1
        self._discard_member_request(guild_id)
        return [("on_member_join", (member,))] if guild is not None else []

    def _parse_guild_member_update(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        user_id = int(data["user"]["id"])
        cached = self.get_member(guild_id, user_id)
        before = _shallow_copy(cached) if cached is not None else None
        user_before, user_key = self._track_user(user_id)
        member = self._member(data, guild_id)
        events = self._user_changed(user_before, user_key, user_id)
        if before is not None:
            events.append(("on_member_update", (before, member)))
        events.append(("on_guild_member_update", (data,)))
        return events

    def _parse_guild_member_remove(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        user = self.store_user(data["user"])
        guild = self.guilds.get(guild_id)
        member = None
        events: _Events = []
        if guild is not None:
            member = guild._members.pop(user.id, None)
            if guild.member_count is not None:
                guild.member_count = max(0, guild.member_count - 1)
            if member is not None:
                events.append(("on_member_remove", (member,)))
        self._discard_member_request(guild_id)
        events.append(
            ("on_raw_member_remove", (RawMemberRemoveEvent(data, member or user),))
        )
        return events

    def _parse_guild_ban_add(self, data: dict[str, Any]) -> _Events:
        guild = self.guilds.get(int(data["guild_id"]))
        events: _Events = []
        if guild is not None and isinstance(data.get("user"), dict):
            user_id = int(data["user"]["id"])
            target = guild.get_member(user_id) or self.store_user(data["user"])
            events.append(("on_member_ban", (guild, target)))
        return events + self._fallback("GUILD_BAN_ADD", data)

    def _parse_guild_ban_remove(self, data: dict[str, Any]) -> _Events:
        guild = self.guilds.get(int(data["guild_id"]))
        events: _Events = []
        if guild is not None and isinstance(data.get("user"), dict):
            events.append(("on_member_unban", (guild, self.store_user(data["user"]))))
        return events + self._fallback("GUILD_BAN_REMOVE", data)

    def _presence(self, raw: RawPresenceUpdateEvent) -> GuildMember | None:
        raw.guild = self.guilds.get(raw.guild_id) if raw.guild_id is not None else None
        return raw.guild.get_member(raw.user_id) if raw.guild is not None else None

    def _parse_presence_update(self, data: dict[str, Any]) -> _Events:
        raw = RawPresenceUpdateEvent(data)
        member = self._presence(raw)
        events: _Events = [("on_raw_presence_update", (raw,))]
        if member is None:
            return events + self._raw("PRESENCE_UPDATE", data)
        before = _shallow_copy(member)
        user_before, user_key = self._track_user(raw.user_id)
        if len(data.get("user", {})) > 1:
            self.store_user(data["user"])
        member._presence_update(raw)
        events.extend(self._user_changed(user_before, user_key, raw.user_id))
        events.append(("on_presence_update", (before, member)))
        return events + self._raw("PRESENCE_UPDATE", data)

    def _parse_presence_update_bulk(self, data: dict[str, Any]) -> _Events:
        # Like presences inside a Discord Guild Create: applied without events.
        guild_id = int(data["guild_id"]) if data.get("guild_id") else None
        for presence in data.get("presences", []):
            raw = RawPresenceUpdateEvent(presence, guild_id=guild_id)
            member = self._presence(raw)
            if member is not None:
                member._presence_update(raw)
        return self._fallback("PRESENCE_UPDATE_BULK", data)

    def _track_member_request(self, guild_id: int, nonce: str, full: bool) -> None:
        for key, request in tuple(self._member_requests.items()):
            if monotonic() - request.started > 60:
                self._discard_member_request(key)
        previous = self._discard_member_request(guild_id)
        guild = self.guilds.get(guild_id)
        if guild is not None:
            guild._member_cache_complete = False
        if (
            guild is not None
            and self.cache_members
            and full
            and isinstance(nonce, str)
            and len(nonce.encode("utf-8")) <= 32
            and (previous is None or previous.nonce != nonce)
        ):
            request = _MemberRequest(nonce, full)
            self._member_requests[guild_id] = request
            try:
                request.timer = asyncio.get_running_loop().call_later(
                    60, self._cancel_member_request, guild_id, nonce
                )
            except RuntimeError:
                pass

    def _discard_member_request(self, guild_id: int) -> _MemberRequest | None:
        request = self._member_requests.pop(guild_id, None)
        if request is not None and request.timer is not None:
            request.timer.cancel()
        return request

    def _cancel_member_request(self, guild_id: int, nonce: str) -> None:
        request = self._member_requests.get(guild_id)
        if request is not None and request.nonce == nonce:
            self._discard_member_request(guild_id)

    def _track_member_ranges(
        self, guild_id: int, selected: dict[str, Any], ranges: list[list[int]]
    ) -> None:
        for target, windows in selected.items():
            windows = windows if isinstance(windows, list) else ranges
            valid = [
                list(window)
                for window in windows
                if isinstance(window, list)
                and len(window) == 2
                and all(isinstance(i, int) for i in window)
                and 0 <= window[0] <= window[1] <= 100000
                and window[1] - window[0] <= 99
            ][:10]
            if valid:
                self._member_ranges[guild_id] = (int(target), valid)
                self._member_lists.pop(guild_id, None)
            elif self._member_ranges.get(guild_id, (None,))[0] == int(target):
                self._member_ranges.pop(guild_id, None)
                self._member_lists.pop(guild_id, None)

    def _parse_guild_members_chunk(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        members = [self._member(item, guild_id) for item in data.get("members", [])]
        for presence in data.get("presences", []):
            raw = RawPresenceUpdateEvent(presence, guild_id=guild_id)
            member = self._presence(raw)
            if member is not None:
                member._presence_update(raw)
        request = self._member_requests.get(guild_id)
        if request is not None and request.nonce == data.get("nonce"):
            index, count = data.get("chunk_index"), data.get("chunk_count")
            if (
                monotonic() - request.started > 60
                or not isinstance(count, int)
                or not isinstance(index, int)
                or not 0 <= index < count <= 100
            ):
                self._discard_member_request(guild_id)
            elif request.count is not None and request.count != count:
                self._discard_member_request(guild_id)
            else:
                request.count = count
                request.chunks[index] = {member.id for member in members}
                if len(request.chunks) == count:
                    self._discard_member_request(guild_id)
                    ids = set().union(*request.chunks.values())
                    guild = self.guilds.get(guild_id)
                    if (
                        guild is not None
                        and request.full
                        and self.cache_members
                        and guild.member_count == len(ids)
                    ):
                        for user_id in tuple(guild._members):
                            if user_id not in ids:
                                del guild._members[user_id]
                        guild._member_cache_complete = True
        return [("on_guild_members_chunk", (data,))]

    def _parse_rate_limited(self, data: dict[str, Any]) -> _Events:
        meta = data.get("meta", {})
        if meta.get("guild_id") is not None:
            if meta.get("nonce") is not None:
                self._cancel_member_request(int(meta["guild_id"]), meta["nonce"])
            else:
                self._discard_member_request(int(meta["guild_id"]))
        return self._fallback("RATE_LIMITED", data)

    def _parse_guild_member_list_update(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        subscription = self._member_ranges.get(guild_id)
        if subscription is not None and str(subscription[0]) == str(data.get("id")):
            allowed = {
                i for start, end in subscription[1] for i in range(start, end + 1)
            }
            positions = self._member_lists.setdefault(guild_id, {})
            for op in data.get("ops", []):
                bounds = op.get("range", [])
                if op.get("op") != "SYNC" or len(bounds) != 2:
                    continue
                start, end = bounds
                if (
                    not isinstance(start, int)
                    or not isinstance(end, int)
                    or not 0 <= start <= end <= 100000
                    or end - start > 99
                ):
                    continue
                for index in range(start, end + 1):
                    positions.pop(index, None)
                for index, item in enumerate(
                    op.get("items", [])[: end - start + 1], start
                ):
                    if index in allowed:
                        if "member" in item:
                            positions[index] = self._member(item["member"], guild_id).id
                        elif "group" in item:
                            positions[index] = dict(item["group"])
        return self._fallback("GUILD_MEMBER_LIST_UPDATE", data)

    # -- Messages ------------------------------------------------------------

    def _parse_message_create(self, data: dict[str, Any]) -> _Events:
        message = self.store_message(Message.from_data(data, self.http))
        channel = self.channels.get(message.channel_id)
        if channel is not None:
            channel.last_message_id = message.id
        return [("on_message", (message,))]

    def _parse_message_update(self, data: dict[str, Any]) -> _Events:
        raw = RawMessageUpdateEvent(data)
        cached = self.get_message(data.get("id"))
        before = _shallow_copy(cached) if cached is not None else None
        message = self.store_message(Message.from_data(data, self.http))
        raw.message = message
        raw.cached_message = before
        events: _Events = [("on_raw_message_edit", (raw,))]
        if before is not None:
            events.append(("on_message_edit", (before, message)))
        return events

    def _parse_message_delete(self, data: dict[str, Any]) -> _Events:
        raw = RawMessageDeleteEvent(data)
        message = self.remove_message(data["id"])
        raw.cached_message = message
        events: _Events = [("on_raw_message_delete", (raw,))]
        if message is not None:
            events.append(("on_message_delete", (message,)))
        return events

    def _parse_message_delete_bulk(self, data: dict[str, Any]) -> _Events:
        raw = RawBulkMessageDeleteEvent(data)
        found = [
            message
            for message in (self.remove_message(item) for item in raw.message_ids)
            if message is not None
        ]
        raw.cached_messages = found
        events: _Events = [("on_raw_bulk_message_delete", (raw,))]
        if found:
            events.append(("on_bulk_message_delete", (found,)))
        events.append(("on_message_delete_bulk", (data,)))
        return events

    def _parse_typing_start(self, data: dict[str, Any]) -> _Events:
        raw = RawTypingEvent(data)
        user: User | GuildMember | None = None
        if raw.guild_id is not None:
            user = self.get_member(raw.guild_id, raw.user_id)
            member_data = data.get("member")
            if user is None and isinstance(member_data, dict):
                user = self._member(
                    {
                        **member_data,
                        "user": member_data.get("user") or {"id": str(raw.user_id)},
                    },
                    raw.guild_id,
                )
        if user is None:
            user = self.users.get(raw.user_id)
        raw.user = user
        channel = self.channels.get(raw.channel_id)
        events: _Events = []
        if channel is not None and user is not None:
            events.append(("on_typing", (channel, user, raw.timestamp)))
        events.append(("on_raw_typing", (raw,)))
        return events + self._fallback("TYPING_START", data)

    # -- Voice ---------------------------------------------------------------

    def _parse_voice_state_update(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"]) if data.get("guild_id") else None
        user_id = int(data["user_id"]) if data.get("user_id") else None
        if guild_id is None or user_id is None:
            # A call participant; Fluxer calls have no discord.py voice event.
            self._store_voice_state(data)
            return []
        previous = self.voice_states.get(guild_id, {}).get(
            (user_id, data.get("connection_id"))
        )
        before = (
            _shallow_copy(previous)
            if previous is not None
            else VoiceState(
                user_id=user_id,
                guild_id=guild_id,
                connection_id=data.get("connection_id"),
            )
        )
        voice, applied = self._apply_voice_state(data)
        if not applied:
            return []
        member: User | GuildMember | None = voice.member or self.get_member(
            guild_id, user_id
        )
        if member is None:
            member = self.store_user({"id": str(user_id)})
        return [("on_voice_state_update", (member, before, voice))]

    # -- Reactions -----------------------------------------------------------

    def _resolve_reaction_member(self, raw: RawReactionActionEvent) -> None:
        if raw.member is not None and raw.member.id == raw.user_id:
            raw.member = self.store_member(raw.member)
        elif raw.guild_id is not None:
            raw.member = self.get_member(raw.guild_id, raw.user_id)

    def _reaction_user(self, raw: RawReactionActionEvent) -> User | GuildMember:
        return (
            raw.member
            or self.users.get(raw.user_id)
            or self.store_user({"id": str(raw.user_id)})
        )

    def _parse_message_reaction_add(self, data: dict[str, Any]) -> _Events:
        raw = RawReactionActionEvent.from_data(data, "REACTION_ADD", self.http)
        self._resolve_reaction_member(raw)
        events: _Events = [("on_raw_reaction_add", (raw,))]
        message = self.get_message(raw.message_id)
        if message is not None:
            reaction = message._add_reaction(data, raw.emoji, raw.user_id)
            if self.user is not None and raw.user_id == self.user.id:
                reaction.me = True
            events.append(("on_reaction_add", (reaction, self._reaction_user(raw))))
        return events

    def _parse_message_reaction_add_many(self, data: dict[str, Any]) -> _Events:
        events: _Events = []
        for reaction in data.get("reactions", []):
            events.extend(self._parse_message_reaction_add({**data, **reaction}))
        return events + self._fallback("MESSAGE_REACTION_ADD_MANY", data)

    def _parse_message_reaction_remove(self, data: dict[str, Any]) -> _Events:
        raw = RawReactionActionEvent.from_data(data, "REACTION_REMOVE", self.http)
        self._resolve_reaction_member(raw)
        events: _Events = [("on_raw_reaction_remove", (raw,))]
        message = self.get_message(raw.message_id)
        if message is not None:
            try:
                reaction = message._remove_reaction(data, raw.emoji, raw.user_id)
            except ValueError:
                return events
            if self.user is not None and raw.user_id == self.user.id:
                reaction.me = False
            events.append(("on_reaction_remove", (reaction, self._reaction_user(raw))))
        return events

    def _parse_message_reaction_remove_all(self, data: dict[str, Any]) -> _Events:
        raw = RawReactionClearEvent.from_data(data)
        events: _Events = [("on_raw_reaction_clear", (raw,))]
        message = self.get_message(raw.message_id)
        if message is not None:
            old_reactions = list(message.reactions)
            message.reactions.clear()
            events.append(("on_reaction_clear", (message, old_reactions)))
        return events

    def _parse_message_reaction_remove_emoji(self, data: dict[str, Any]) -> _Events:
        raw = RawReactionClearEmojiEvent.from_data(data, self.http)
        events: _Events = [("on_raw_reaction_clear_emoji", (raw,))]
        message = self.get_message(raw.message_id)
        if message is not None:
            reaction = message._clear_emoji(raw.emoji)
            if reaction is not None:
                events.append(("on_reaction_clear_emoji", (reaction,)))
        return events


__all__ = ("ConnectionState",)
