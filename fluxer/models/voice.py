from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .member import GuildMember

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class VoiceState:
    """Represents a user's voice state in a guild."""

    user_id: int
    guild_id: int | None = None
    channel_id: int | None = None
    session_id: str | None = None
    mute: bool = False
    deaf: bool = False
    self_mute: bool = False
    self_deaf: bool = False
    self_stream: bool = False
    self_video: bool = False
    suppress: bool = False
    request_to_speak_timestamp: str | None = None
    member: GuildMember | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> VoiceState:
        return cls(
            user_id=int(data["user_id"]),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            channel_id=int(data["channel_id"]) if data.get("channel_id") else None,
            session_id=data.get("session_id"),
            mute=data.get("mute", False),
            deaf=data.get("deaf", False),
            self_mute=data.get("self_mute", False),
            self_deaf=data.get("self_deaf", False),
            self_stream=data.get("self_stream", False),
            self_video=data.get("self_video", False),
            suppress=data.get("suppress", False),
            request_to_speak_timestamp=data.get("request_to_speak_timestamp"),
            member=(
                GuildMember.from_data(data["member"], http)
                if data.get("member")
                else None
            ),
        )
