from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RawFluxerEvent:
    """Typed fallback for Fluxer gateway events without first-class models yet."""

    name: str
    data: Any


@dataclass(slots=True)
class SavedMessageEvent(RawFluxerEvent):
    pass


@dataclass(slots=True)
class FavoriteMemeEvent(RawFluxerEvent):
    pass


@dataclass(slots=True)
class RelationshipEvent(RawFluxerEvent):
    pass


@dataclass(slots=True)
class UserSettingsEvent(RawFluxerEvent):
    pass


@dataclass(slots=True)
class GuildMemberListUpdateEvent(RawFluxerEvent):
    pass


@dataclass(slots=True)
class ChannelUpdateBulkEvent(RawFluxerEvent):
    pass


@dataclass(slots=True)
class GuildRoleUpdateBulkEvent(RawFluxerEvent):
    pass


@dataclass(slots=True)
class EntranceSoundPlayEvent(RawFluxerEvent):
    pass


@dataclass(slots=True)
class RecentMentionDeleteEvent(RawFluxerEvent):
    pass


def fluxer_event_from_dispatch(name: str, data: Any) -> RawFluxerEvent:
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
