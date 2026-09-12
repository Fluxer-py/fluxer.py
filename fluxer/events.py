"""Events helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RawFluxerEvent:
    """Typed fallback for Fluxer gateway events without first-class models yet.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    name: str
    data: Any


@dataclass(slots=True)
class SavedMessageEvent(RawFluxerEvent):
    """Saved Message Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


@dataclass(slots=True)
class FavoriteMemeEvent(RawFluxerEvent):
    """Favorite Meme Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


@dataclass(slots=True)
class RelationshipEvent(RawFluxerEvent):
    """Relationship Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


@dataclass(slots=True)
class UserSettingsEvent(RawFluxerEvent):
    """User Settings Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


@dataclass(slots=True)
class GuildMemberListUpdateEvent(RawFluxerEvent):
    """Guild Member List Update Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


@dataclass(slots=True)
class ChannelUpdateBulkEvent(RawFluxerEvent):
    """Channel Update Bulk Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


@dataclass(slots=True)
class GuildRoleUpdateBulkEvent(RawFluxerEvent):
    """Guild Role Update Bulk Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


@dataclass(slots=True)
class EntranceSoundPlayEvent(RawFluxerEvent):
    """Entrance Sound Play Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


@dataclass(slots=True)
class RecentMentionDeleteEvent(RawFluxerEvent):
    """Recent Mention Delete Event data and behaviour.

    Attributes:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    pass


def fluxer_event_from_dispatch(name: str, data: Any) -> RawFluxerEvent:
    """Wrap a raw dispatch in the existing typed event family.

    Args:
        name: Name to assign or resolve in this operation.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

    Returns:
        The result of this operation.
    """
    if name.startswith("SAVED_MESSAGE_"):
        return SavedMessageEvent(name, data)
    if name.startswith("FAVORITE_MEME_"):
        return FavoriteMemeEvent(name, data)
    if name.startswith("RELATIONSHIP_"):
        return RelationshipEvent(name, data)
    if name.startswith("USER_") or name in {
        "AUTH_SESSION_CHANGE",
        "WEBAUTHN_CREDENTIALS_UPDATE",
    }:
        return UserSettingsEvent(name, data)
    if name == "GUILD_MEMBER_LIST_UPDATE":
        return GuildMemberListUpdateEvent(name, data)
    if name == "CHANNEL_UPDATE_BULK":
        return ChannelUpdateBulkEvent(name, data)
    if name == "GUILD_ROLE_UPDATE_BULK":
        return GuildRoleUpdateBulkEvent(name, data)
    if name == "ENTRANCE_SOUND_PLAY":
        return EntranceSoundPlayEvent(name, data)
    if name == "RECENT_MENTION_DELETE":
        return RecentMentionDeleteEvent(name, data)
    return RawFluxerEvent(name, data)


__all__ = (
    "RawFluxerEvent",
    "SavedMessageEvent",
    "FavoriteMemeEvent",
    "RelationshipEvent",
    "UserSettingsEvent",
    "GuildMemberListUpdateEvent",
    "ChannelUpdateBulkEvent",
    "GuildRoleUpdateBulkEvent",
    "EntranceSoundPlayEvent",
    "RecentMentionDeleteEvent",
    "fluxer_event_from_dispatch",
)
