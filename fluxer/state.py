from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .models import Channel, Guild, GuildMember, Message, VoiceState


@dataclass(slots=True)
class ConnectionState:
    """Small Fluxer cache/state container used by Client dispatch."""

    http: Any | None = None
    max_messages: int = 1000
    cache_members: bool = True
    guilds: dict[int, Guild] = field(default_factory=dict)
    channels: dict[int, Channel] = field(default_factory=dict)
    members: dict[tuple[int, int], GuildMember] = field(default_factory=dict)
    messages: OrderedDict[int, Message] = field(default_factory=OrderedDict)
    voice_states: dict[int, dict[tuple[int, str | None], VoiceState]] = field(
        default_factory=dict
    )

    def store_guild(self, guild: Guild) -> Guild:
        self.guilds[guild.id] = guild
        return guild

    def store_channel(self, channel: Channel) -> Channel:
        if channel.guild_id is not None:
            channel._guild = self.guilds.get(channel.guild_id)
        self.channels[channel.id] = channel
        return channel

    def store_member(self, member: GuildMember) -> GuildMember:
        if self.cache_members and member.guild_id is not None:
            self.members[(member.guild_id, member.user.id)] = member
        return member

    def get_member(self, guild_id: int | None, user_id: int) -> GuildMember | None:
        if guild_id is None:
            return None
        return self.members.get((guild_id, user_id))

    def store_message(self, message: Message) -> Message:
        cached_channel = self.channels.get(message.channel_id)
        if cached_channel:
            message._channel = cached_channel
        guild_id = message.guild_id or (
            cached_channel.guild_id if cached_channel else None
        )
        if guild_id is not None:
            message._cache_guild(self.guilds.get(guild_id))
        if self.max_messages > 0:
            self.messages[message.id] = message
            self.messages.move_to_end(message.id)
            while len(self.messages) > self.max_messages:
                self.messages.popitem(last=False)
        return message

    def get_message(self, message_id: int | str | None) -> Message | None:
        if message_id is None:
            return None
        try:
            return self.messages.get(int(message_id))
        except (TypeError, ValueError):
            return None

    def remove_message(self, message_id: int | str | None) -> Message | None:
        if message_id is None:
            return None
        try:
            return self.messages.pop(int(message_id), None)
        except (TypeError, ValueError):
            return None
