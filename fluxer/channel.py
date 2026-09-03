from __future__ import annotations

from .enums import ChannelType
from .models.channel import Channel

TextChannel = Channel
VoiceChannel = Channel
CategoryChannel = Channel
DMChannel = Channel
GroupChannel = Channel


def _channel_factory(channel_type: int):
    try:
        return Channel, ChannelType(channel_type)
    except ValueError:
        return Channel, channel_type


__all__ = (
    "Channel",
    "TextChannel",
    "VoiceChannel",
    "CategoryChannel",
    "DMChannel",
    "GroupChannel",
    "_channel_factory",
)
