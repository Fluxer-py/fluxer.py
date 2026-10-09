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
from typing import TYPE_CHECKING, Any
from weakref import WeakValueDictionary

from ._types import UNSET, UnsetType
from .events import fluxer_event_from_dispatch
from .models import Channel, Guild, GuildMember, Message, User, VoiceState
from .models.role import Role
from .models.reaction import (
    RawReactionActionEvent,
    RawReactionClearEvent,
    RawReactionClearEmojiEvent,
)

if TYPE_CHECKING:
    from .http import HTTPClient

_Events = list[tuple[str, tuple[Any, ...]]]
_VoiceKey = tuple[int, int, str | None]


@lru_cache(maxsize=None)
def _field_names(cls: type) -> tuple[str, ...]:
    return tuple(item.name for item in fields(cls) if not item.name.startswith("_"))


def _update(target: Any, source: Any, *, exclude: tuple[str, ...] = ()) -> Any:
    for name in _field_names(type(source)):
        if name not in exclude:
            setattr(target, name, getattr(source, name))
    return target


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
    """

    http: HTTPClient | None = None
    max_messages: int = 1000
    cache_members: bool = True
    max_private_channels: int | None | UnsetType = UNSET
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
                exclude=("roles", "channels", "members", "emojis", "stickers"),
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
        voice = VoiceState.from_data(data, self.http)
        if voice.guild_id is None or voice.user_id is None:
            return voice
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
                return previous
            voice.channel_id = None
            voice.version = version
            return voice
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
        return voice

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
        collections = ("roles", "channels", "members", "emojis", "stickers")
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
        self.user = self.store_user(data)
        return self._fallback("USER_UPDATE", data)

    def _parse_guild_create(self, data: dict[str, Any]) -> _Events:
        return [
            (
                "on_guild_join",
                (
                    self._guild_snapshot(
                        {"unavailable": False, "unavailable_hidden": False, **data}
                    ),
                ),
            )
        ]

    def _parse_guild_sync(self, data: dict[str, Any]) -> _Events:
        self._guild_snapshot(
            {"unavailable": False, "unavailable_hidden": False, **data}
        )
        return self._fallback("GUILD_SYNC", data)

    def _parse_guild_update(self, data: dict[str, Any]) -> _Events:
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
        return self._fallback("GUILD_UPDATE", data)

    def _parse_guild_delete(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["id"])
        guild = self.guilds.get(guild_id)
        if data.get("unavailable", False):
            guild = self._guild_snapshot(data)
            guild._member_cache_complete = False
        else:
            if guild is not None:
                for channel_id in tuple(guild._channels):
                    self._remove_channel(channel_id)
            for message_id in tuple(self._guild_messages.get(guild_id, ())):
                self.remove_message(message_id)
            self._clear_guild_voice(guild_id)
            self.guilds.pop(guild_id, None)
        self._discard_member_request(guild_id)
        self._member_ranges.pop(guild_id, None)
        self._member_lists.pop(guild_id, None)
        return [("on_guild_remove", (guild or data,))]

    def _parse_channel_create(self, data: dict[str, Any]) -> _Events:
        return [
            (
                "on_channel_create",
                (self.store_channel(Channel.from_data(data, self.http)),),
            )
        ]

    def _parse_channel_update(self, data: dict[str, Any]) -> _Events:
        return [
            (
                "on_channel_update",
                (self.store_channel(Channel.from_data(data, self.http)),),
            )
        ]

    def _parse_channel_update_bulk(self, data: dict[str, Any]) -> _Events:
        for channel in data.get("channels", []):
            self.store_channel(
                Channel.from_data(
                    {"guild_id": data.get("guild_id"), **channel}, self.http
                )
            )
        return [
            (
                "on_fluxer_event",
                (fluxer_event_from_dispatch("CHANNEL_UPDATE_BULK", data),),
            )
        ]

    def _parse_channel_delete(self, data: dict[str, Any]) -> _Events:
        return [("on_channel_delete", (self._remove_channel(int(data["id"])) or data,))]

    def _member(self, data: dict[str, Any], guild_id: int) -> GuildMember:
        return self.store_member(
            GuildMember.from_data(data, self.http, guild_id=guild_id)
        )

    def _parse_guild_member_add(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        self._member(data, guild_id)
        guild = self.guilds.get(guild_id)
        if guild is not None and guild.member_count is not None:
            guild.member_count += 1
        self._discard_member_request(guild_id)
        return [("on_member_join", (data,))]

    def _parse_guild_member_update(self, data: dict[str, Any]) -> _Events:
        self._member(data, int(data["guild_id"]))
        return [("on_guild_member_update", (data,))]

    def _parse_guild_member_remove(self, data: dict[str, Any]) -> _Events:
        guild_id = int(data["guild_id"])
        guild = self.guilds.get(guild_id)
        if guild is not None:
            guild._members.pop(int(data["user"]["id"]), None)
            if guild.member_count is not None:
                guild.member_count = max(0, guild.member_count - 1)
        self._discard_member_request(guild_id)
        return [("on_member_remove", (data,))]

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

    def _role_update(self, data: dict[str, Any], roles: list[dict[str, Any]]) -> None:
        guild = self.guilds.get(int(data["guild_id"]))
        if guild is not None:
            for payload in roles:
                role = Role.from_data(payload, self.http, guild.id)
                previous = guild._roles.get(role.id)
                guild._roles[role.id] = (
                    _update(previous, role) if previous is not None else role
                )

    def _parse_guild_role_create(self, data: dict[str, Any]) -> _Events:
        self._role_update(data, [data["role"]])
        return self._fallback("GUILD_ROLE_CREATE", data)

    def _parse_guild_role_update(self, data: dict[str, Any]) -> _Events:
        self._role_update(data, [data["role"]])
        return self._fallback("GUILD_ROLE_UPDATE", data)

    def _parse_guild_role_update_bulk(self, data: dict[str, Any]) -> _Events:
        self._role_update(data, data.get("roles", []))
        return [
            (
                "on_fluxer_event",
                (fluxer_event_from_dispatch("GUILD_ROLE_UPDATE_BULK", data),),
            )
        ]

    def _parse_guild_role_delete(self, data: dict[str, Any]) -> _Events:
        guild = self.guilds.get(int(data["guild_id"]))
        if guild is not None:
            role_id = int(data["role_id"])
            guild._roles.pop(role_id, None)
            for member in guild.members:
                if role_id in member.roles:
                    member.roles.remove(role_id)
        return self._fallback("GUILD_ROLE_DELETE", data)

    def _parse_guild_emojis_update(self, data: dict[str, Any]) -> _Events:
        self._guild_snapshot({"id": data["guild_id"], "emojis": data.get("emojis", [])})
        return self._fallback("GUILD_EMOJIS_UPDATE", data)

    def _parse_guild_stickers_update(self, data: dict[str, Any]) -> _Events:
        self._guild_snapshot(
            {"id": data["guild_id"], "stickers": data.get("stickers", [])}
        )
        return self._fallback("GUILD_STICKERS_UPDATE", data)

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

    def _parse_channel_pins_update(self, data: dict[str, Any]) -> _Events:
        channel = self.channels.get(int(data["channel_id"]))
        if channel is not None:
            channel.last_pin_timestamp = data.get("last_pin_timestamp")
        return self._fallback("CHANNEL_PINS_UPDATE", data)

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

    def _parse_message_create(self, data: dict[str, Any]) -> _Events:
        message = self.store_message(Message.from_data(data, self.http))
        channel = self.channels.get(message.channel_id)
        if channel is not None:
            channel.last_message_id = message.id
        return [("on_message", (message,))]

    def _parse_message_update(self, data: dict[str, Any]) -> _Events:
        return [
            (
                "on_message_edit",
                (self.store_message(Message.from_data(data, self.http)),),
            )
        ]

    def _parse_message_delete(self, data: dict[str, Any]) -> _Events:
        self.remove_message(data["id"])
        return [("on_message_delete", (data,))]

    def _parse_message_delete_bulk(self, data: dict[str, Any]) -> _Events:
        for message_id in data.get("ids", []):
            self.remove_message(message_id)
        return [("on_message_delete_bulk", (data,))]

    def _parse_voice_state_update(self, data: dict[str, Any]) -> _Events:
        return [("on_voice_state_update", (self._store_voice_state(data),))]

    def _parse_message_reaction_add(self, data: dict[str, Any]) -> _Events:
        raw = RawReactionActionEvent.from_data(data, "REACTION_ADD", self.http)
        events: _Events = []
        user: User | GuildMember | None = self.users.get(raw.user_id)
        if raw.member is not None and raw.member.id == raw.user_id:
            raw.member = self.store_member(raw.member)
            user = raw.member
        elif raw.guild_id is not None:
            raw.member = self.get_member(raw.guild_id, raw.user_id)
            user = raw.member or user
        message = self.get_message(raw.message_id)
        if message is not None:
            reaction = message._add_reaction(data, raw.emoji, raw.user_id)
            if self.user is not None and raw.user_id == self.user.id:
                reaction.me = True
            if user is None:
                user = self.store_user({"id": str(raw.user_id)})
            events.append(("on_reaction_add", (reaction, user)))
        events.append(("on_raw_reaction_add", (raw,)))
        return events

    def _parse_message_reaction_add_many(self, data: dict[str, Any]) -> _Events:
        events: _Events = []
        for reaction in data.get("reactions", []):
            events.extend(self._parse_message_reaction_add({**data, **reaction}))
        return events + self._fallback("MESSAGE_REACTION_ADD_MANY", data)

    def _parse_message_reaction_remove(self, data: dict[str, Any]) -> _Events:
        raw = RawReactionActionEvent.from_data(data, "REACTION_REMOVE", self.http)
        if raw.member is not None and raw.member.id == raw.user_id:
            raw.member = self.store_member(raw.member)
        message = self.get_message(raw.message_id)
        if message is not None:
            try:
                message._remove_reaction(data, raw.emoji, raw.user_id)
            except ValueError:
                pass
        return [("on_raw_reaction_remove", (raw,))]

    def _parse_message_reaction_remove_all(self, data: dict[str, Any]) -> _Events:
        raw = RawReactionClearEvent.from_data(data)
        message = self.get_message(raw.message_id)
        if message is not None:
            message.reactions.clear()
        return [("on_raw_reaction_clear", (raw,))]

    def _parse_message_reaction_remove_emoji(self, data: dict[str, Any]) -> _Events:
        raw = RawReactionClearEmojiEvent.from_data(data, self.http)
        message = self.get_message(raw.message_id)
        if message is not None:
            message._clear_emoji(raw.emoji)
        return [("on_raw_reaction_clear_emoji", (raw,))]


__all__ = ("ConnectionState",)
