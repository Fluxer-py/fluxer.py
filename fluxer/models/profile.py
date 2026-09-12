"""Profile helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .._endpoints import asset_url

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .user import User
from .member import GuildMember

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class UserProfile:
    """Represents a Fluxer user's full profile.

    This contains profile information that is only available via the
    GET /users/{id}/profile endpoint, not from basic user objects.

    Attributes:
        user: The public representation of the target account.
        bio: The account-wide biography, or null when none is set.
        pronouns: The account-wide pronouns, or null when none are set.
        banner: The image hash of the profile banner, or null when none is set.
        banner_color: The packed 24-bit RGB colour derived from the stored banner, or null.
        accent_color: The profile accent colour as packed 24-bit RGB, or null when none is set.
        premium_type: The premium type visible to the caller.
        premium_since: The premium activation time visible to the caller.
        premium_lifetime_sequence: The lifetime premium sequence visible to the caller.
        guild_member: The membership the target account holds in the named guild.
        guild_member_profile: The per-guild profile customisation of the target account.
        timezone_offset: The offset of the target profile timezone in minutes from UTC, or null.
        profile_limited: Whether profile privacy removed restricted fields.
        mutual_friends: The mutual friends in descending account identifier order.
        mutual_guilds: The guilds the caller and the target are both members of.
        raw_data: Original payload preserving absent versus explicit-null privacy fields; excluded from repr.
        connected_accounts: The verified connections the caller is permitted to see.
        banner_url: URL for the user's banner, or None if they don't have one.
        is_premium: Whether this user has premium.
    """

    # The basic user object
    user: User

    # Profile information
    bio: str | None = None
    pronouns: str | None = None
    banner: str | None = None  # Banner image hash
    banner_color: int | None = None
    accent_color: int | None = None

    # Premium information
    premium_type: int | None = None
    premium_since: str | None = None  # ISO 8601 timestamp
    premium_lifetime_sequence: int | None = None

    guild_member: GuildMember | None = None
    guild_member_profile: dict[str, Any] | None = None
    timezone_offset: int | None = None
    profile_limited: bool | None = None
    mutual_friends: list[User] | None = None
    mutual_guilds: list[dict[str, Any]] | None = None
    connected_accounts: list[dict[str, Any]] = field(default_factory=list)

    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    # Back-reference (set after construction)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        guild_id: int | None = None,
    ) -> UserProfile:
        """Construct a UserProfile from raw API data.

        Args:
            data: Raw profile object from GET /users/{id}/profile
            http: HTTPClient for making further requests
            guild_id: Identity of the guild used by this operation.

        Returns:
            A new UserProfile instance
        """
        # Parse the nested user object
        user = User.from_data(data["user"], http)

        # Get the user_profile section
        profile_data = data.get("user_profile", {})

        return cls(
            user=user,
            bio=profile_data.get("bio"),
            pronouns=profile_data.get("pronouns"),
            banner=profile_data.get("banner"),
            banner_color=profile_data.get("banner_color"),
            accent_color=profile_data.get("accent_color"),
            premium_type=data.get("premium_type"),
            premium_since=data.get("premium_since"),
            premium_lifetime_sequence=data.get("premium_lifetime_sequence"),
            guild_member=GuildMember.from_data(
                {"user": data["user"], **data["guild_member"]}, http, guild_id=guild_id
            )
            if data.get("guild_member") is not None
            else None,
            guild_member_profile=data.get("guild_member_profile"),
            timezone_offset=data.get("timezone_offset"),
            profile_limited=data.get("profile_limited"),
            mutual_friends=[
                User.from_data(user, http) for user in data["mutual_friends"]
            ]
            if data.get("mutual_friends") is not None
            else None,
            mutual_guilds=data.get("mutual_guilds"),
            connected_accounts=list(data.get("connected_accounts", [])),
            raw_data=dict(data),
            _http=http,
        )

    @property
    def banner_url(self) -> str | None:
        """URL for the user's banner, or None if they don't have one.

        Returns:
            The result of this operation.
        """
        if self.banner:
            ext = "gif" if self.banner.startswith("a_") else "png"
            return asset_url(
                self._http, "media", f"banners/{self.user.id}/{self.banner}.{ext}"
            )
        return None

    @property
    def is_premium(self) -> bool:
        """Whether this user has premium.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.premium_type is not None and self.premium_type > 0

    def __str__(self) -> str:
        """Return the user's display name.

        Returns:
            The result of this operation.
        """
        return self.user.display_name


__all__ = ("UserProfile",)
