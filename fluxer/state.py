"""Bounded message, guild, channel, member, and voice caches owned by a client.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .http import HTTPClient

from .models import Channel, Guild, GuildMember, Message, VoiceState


@dataclass(slots=True)
class ConnectionState:
    """Small Fluxer cache/state container used by Client dispatch.

    Attributes:
        http: Transport to bind for subsequent operations; None creates an unbound model.
        max_messages: Maximum number of messages retained in insertion order.
        cache_members: Whether parsed memberships are retained between events.
        guilds: Guilds used by this operation.
        channels: Cached channel snapshots keyed by channel ID.
        members: Members used by this operation.
        messages: Messages used by this operation.
        voice_states: Voice states used by this operation.
    """

    http: HTTPClient | None = None
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
        """Replace the cached guild with this parsed snapshot.

        Args:
            guild: Guild supplying role and channel context.

        Returns:
            The result of this operation.
        """
        self.guilds[guild.id] = guild
        return guild

    def store_channel(self, channel: Channel) -> Channel:
        """Cache a channel and attach its known guild context.

        Args:
            channel: Channel in which the operation takes place.

        Returns:
            The result of this operation.
        """
        if channel.guild_id is not None:
            channel._guild = self.guilds.get(channel.guild_id)
        self.channels[channel.id] = channel
        return channel

    def store_member(self, member: GuildMember) -> GuildMember:
        """Cache a guild member when member caching is enabled.

        Args:
            member: Member used by this operation.

        Returns:
            The result of this operation.
        """
        if self.cache_members and member.guild_id is not None:
            self.members[(member.guild_id, member.user.id)] = member
        return member

    def get_member(self, guild_id: int | None, user_id: int) -> GuildMember | None:
        """Get member.

        Args:
            guild_id: Identity of the guild used by this operation.
            user_id: Identity of the user used by this operation.

        Returns:
            The requested member, or None when no matching value is available.
        """
        if guild_id is None:
            return None
        return self.members.get((guild_id, user_id))

    def store_message(self, message: Message) -> Message:
        """Bind message context and retain it within the configured cache bound.

        Args:
            message: Message supplying content and channel/guild context.

        Returns:
            The result of this operation.
        """
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
        """Get message.

        Args:
            message_id: Identity of the message used by this operation.

        Returns:
            The requested message, or None when no matching value is available.
        """
        if message_id is None:
            return None
        try:
            return self.messages.get(int(message_id))
        except (TypeError, ValueError):
            return None

    def remove_message(self, message_id: int | str | None) -> Message | None:
        """Remove and return a cached message, if it exists.

        Args:
            message_id: Identity of the message used by this operation.

        Returns:
            The result of this operation.
        """
        if message_id is None:
            return None
        try:
            return self.messages.pop(int(message_id), None)
        except (TypeError, ValueError):
            return None


__all__ = ("ConnectionState",)
