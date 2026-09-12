"""Optional LiveKit voice connections and FFmpeg PCM playback.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .member import GuildMember

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class VoiceState:
    """Represents a user's voice state in a guild.

    Attributes:
        user_id: Identity of the user used by this operation.
        guild_id: Guild identity retained from the payload or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        connection_id: Connection identity issued by the voice grant, required when leaving.
        session_id: Identity of the session used by this operation.
        mute: Whether the guild moderator mute applies to this member.
        deaf: Whether the guild moderator deafen applies to this member.
        self_mute: Whether this voice connection starts with the local microphone muted.
        self_deaf: Whether this voice connection starts locally deafened.
        self_stream: Self stream used by this operation.
        self_video: Self video used by this operation.
        suppress: Suppress used by this operation.
        request_to_speak_timestamp: Request to speak timestamp used by this operation.
        member: Member used by this operation.
        is_mobile: Is mobile used by this operation.
        viewer_stream_keys: Viewer stream keys used by this operation.
        e2ee_capable: E2ee capable used by this operation.
        version: Version used by this operation.
    """

    user_id: int | None
    guild_id: int | None = None
    channel_id: int | None = None
    connection_id: str | None = None
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

    is_mobile: bool = False
    viewer_stream_keys: list[str] = field(default_factory=list)
    e2ee_capable: bool = False
    version: int | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> VoiceState:
        """Build a VoiceState from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed VoiceState instance.
        """
        return cls(
            user_id=int(data["user_id"]) if data.get("user_id") is not None else None,
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            channel_id=int(data["channel_id"]) if data.get("channel_id") else None,
            connection_id=data.get("connection_id"),
            session_id=data.get("session_id"),
            is_mobile=data.get("is_mobile", False),
            viewer_stream_keys=list(data.get("viewer_stream_keys", [])),
            e2ee_capable=data.get("e2ee_capable", False),
            version=data.get("version"),
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


__all__ = ("VoiceState",)
