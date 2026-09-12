"""Invite helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from ._endpoints import asset_url

if TYPE_CHECKING:
    from .http import HTTPClient


@dataclass(slots=True)
class Invite:
    """Invite data and behaviour.

    Attributes:
        code: The unique code that identifies the invite.
        guild_id: Guild identity retained from the payload or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        inviter_id: Identity of the inviter used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        type: Invite type.
        member_count: The member count of the guild, or the exact recipient count of the group direct message.
        presence_count: The online member count of the guild.
        expires_at: The time at which the invite stops resolving, or null when it never expires.
        temporary: Whether admission through this invite grants temporary membership.
        created_at: The time at which the invite record was created.
        uses: The number of admissions completed through the invite.
        max_uses: The maximum admissions the invite permits, where `0` is unlimited.
        max_age: The stored lifetime in seconds, where `0` never expires.
        guild: The guild the invite admits into.
        channel: The guild channel or group direct message the invite targets.
        inviter: The account that created the invite, or null.
        url: Url.
    """

    code: str
    guild_id: int | None = None
    channel_id: int | None = None
    inviter_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)
    type: int | None = None
    member_count: int | None = None
    presence_count: int | None = None
    expires_at: str | None = None
    temporary: bool | None = None
    created_at: str | None = None
    uses: int | None = None
    max_uses: int | None = None
    max_age: int | None = None
    guild: dict[str, Any] | None = None
    channel: dict[str, Any] | None = None
    inviter: dict[str, Any] | None = None

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> "Invite":
        """Build a Invite from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Invite instance.
        """
        guild = data.get("guild") or data.get("guild_id")
        channel = data.get("channel") or data.get("channel_id")
        inviter = data.get("inviter") or data.get("inviter_id")
        return cls(
            code=data.get("code") or data.get("invite_code") or "",
            guild_id=int(guild["id"] if isinstance(guild, dict) else guild)
            if guild
            else None,
            channel_id=int(channel["id"] if isinstance(channel, dict) else channel)
            if channel
            else None,
            inviter_id=int(inviter["id"] if isinstance(inviter, dict) else inviter)
            if inviter
            else None,
            raw_data=dict(data),
            type=data.get("type"),
            member_count=data.get("member_count"),
            presence_count=data.get("presence_count"),
            expires_at=data.get("expires_at"),
            temporary=data.get("temporary"),
            created_at=data.get("created_at"),
            uses=data.get("uses"),
            max_uses=data.get("max_uses"),
            max_age=data.get("max_age"),
            guild=data.get("guild"),
            channel=data.get("channel"),
            inviter=data.get("inviter"),
            _http=http,
        )

    @property
    def url(self) -> str:
        """Url.

        Returns:
            The result of this operation.
        """
        return asset_url(self._http, "invite", quote(self.code, safe=""))

    async def delete(self) -> None:
        """Delete.

        Returns:
            None.
        """
        if self._http is None:
            raise RuntimeError("Invite is not bound to an HTTP client")
        await self._http.delete_invite(self.code)

    def __str__(self) -> str:
        """Return the object's user-facing text representation.

        Returns:
            The result of this operation.
        """
        return self.url


__all__ = ("Invite",)
