"""Invite helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from ._endpoints import asset_url
from .asset import _GuildImages
from .models.user import User

if TYPE_CHECKING:
    from .http import HTTPClient


@dataclass(slots=True)
class PartialGuild(_GuildImages):
    """The public summary of a guild, as embedded in an invite.

    Attributes:
        id: Guild ID.
        name: Guild name.
        icon_hash: Icon image hash, or None.
        banner_hash: Banner image hash, or None.
        banner_width: Banner width in pixels, or None.
        banner_height: Banner height in pixels, or None.
        splash_hash: Invite splash image hash, or None.
        splash_width: Splash width in pixels, or None.
        splash_height: Splash height in pixels, or None.
        splash_card_alignment: Alignment of the invite splash card.
        embed_splash_hash: Embed splash image hash, or None.
        embed_splash_width: Embed splash width in pixels, or None.
        embed_splash_height: Embed splash height in pixels, or None.
        features: Enabled guild features.
        icon_url: URL of the guild icon, or None.
        icon: The guild icon asset, or None.
        banner: The guild banner asset, or None.
        splash: The invite splash asset, or None.
        embed_splash: The embedded invite splash asset, or None.
        banner_url: URL of the guild banner, or None.
        splash_url: URL of the invite splash, or None.
        embed_splash_url: URL of the embedded invite splash, or None.
    """

    id: int
    name: str = ""
    icon_hash: str | None = None
    banner_hash: str | None = None
    banner_width: int | None = None
    banner_height: int | None = None
    splash_hash: str | None = None
    splash_width: int | None = None
    splash_height: int | None = None
    splash_card_alignment: int = 0
    embed_splash_hash: str | None = None
    embed_splash_width: int | None = None
    embed_splash_height: int | None = None
    features: list[str] = field(default_factory=list)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> PartialGuild:
        """Build a PartialGuild from its decoded payload.

        Args:
            data: Partial guild object.
            http: Transport used to build asset URLs.

        Returns:
            The parsed guild summary.
        """
        return cls(
            id=int(data["id"]),
            name=data.get("name") or "",
            icon_hash=data.get("icon"),
            banner_hash=data.get("banner"),
            banner_width=data.get("banner_width"),
            banner_height=data.get("banner_height"),
            splash_hash=data.get("splash"),
            splash_width=data.get("splash_width"),
            splash_height=data.get("splash_height"),
            splash_card_alignment=data.get("splash_card_alignment", 0),
            embed_splash_hash=data.get("embed_splash"),
            embed_splash_width=data.get("embed_splash_width"),
            embed_splash_height=data.get("embed_splash_height"),
            features=list(data.get("features", [])),
            _http=http,
        )


@dataclass(slots=True)
class PartialInviteRecipient:
    """A group DM recipient listed on an invite.

    Attributes:
        username: The recipient's username.
    """

    username: str

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> PartialInviteRecipient:
        """Build a PartialInviteRecipient from its decoded payload.

        Args:
            data: Partial invite recipient object.

        Returns:
            The parsed recipient.
        """
        return cls(username=data.get("username", ""))


@dataclass(slots=True)
class PartialInviteChannel:
    """The channel an invite targets.

    Attributes:
        id: Channel ID.
        name: Channel name, or None (group DMs may have none).
        type: Channel type.
        recipients: Group DM recipients, when the invite targets a group DM.
    """

    id: int
    name: str | None = None
    type: int = 0
    recipients: list[PartialInviteRecipient] = field(default_factory=list)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> PartialInviteChannel:
        """Build a PartialInviteChannel from its decoded payload.

        Args:
            data: Partial invite channel object.

        Returns:
            The parsed channel summary.
        """
        return cls(
            id=int(data["id"]),
            name=data.get("name"),
            type=data.get("type", 0),
            recipients=[
                PartialInviteRecipient.from_data(item)
                for item in data.get("recipients", [])
            ],
        )


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
    guild: PartialGuild | None = None
    channel: PartialInviteChannel | None = None
    inviter: User | None = None

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
            guild=PartialGuild.from_data(guild, http)
            if isinstance(guild, dict)
            else None,
            channel=PartialInviteChannel.from_data(channel)
            if isinstance(channel, dict)
            else None,
            inviter=User.from_data(inviter, http)
            if isinstance(inviter, dict)
            else None,
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


__all__ = ("Invite", "PartialGuild", "PartialInviteChannel", "PartialInviteRecipient")
