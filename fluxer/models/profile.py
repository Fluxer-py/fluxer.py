"""Profile helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from ..asset import Asset

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..fluxer_models import UserConnection
from .user import User
from .member import GuildMember

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class GuildMemberProfile:
    """Per-guild profile customisation of an account.

    Attributes:
        bio: Guild-specific biography, or None.
        pronouns: Guild-specific pronouns, or None.
        banner_hash: Guild-specific banner image hash, or None.
        banner: The guild-specific banner asset, or None.
        banner_url: URL of the guild-specific banner, or None.
        accent_color: Guild-specific accent colour as packed 24-bit RGB, or None.
    """

    bio: str | None = None
    pronouns: str | None = None
    banner_hash: str | None = None
    accent_color: int | None = None
    _http: HTTPClient | None = field(default=None, repr=False, compare=False)
    _guild_id: int | None = field(default=None, repr=False, compare=False)
    _user_id: int | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        guild_id: int | None = None,
        user_id: int | None = None,
    ) -> GuildMemberProfile:
        """Build a GuildMemberProfile from its decoded payload.

        Args:
            data: Guild member profile object.
            http: Transport used to build asset URLs.
            guild_id: Guild the profile belongs to.
            user_id: Account the profile belongs to.

        Returns:
            The parsed profile.
        """
        return cls(
            bio=data.get("bio"),
            pronouns=data.get("pronouns"),
            banner_hash=data.get("banner"),
            accent_color=data.get("accent_color"),
            _http=http,
            _guild_id=guild_id,
            _user_id=user_id,
        )

    @property
    def banner(self) -> Asset | None:
        """The guild-specific banner, or None when none is set or it cannot be addressed.

        Returns:
            The banner asset, when set and the guild and account are known.
        """
        if not self.banner_hash or self._guild_id is None or self._user_id is None:
            return None
        return Asset._from_guild_member_banner(
            self._http, self._guild_id, self._user_id, self.banner_hash
        )

    @property
    def banner_url(self) -> str | None:
        """URL of :attr:`banner`, or None.

        Returns:
            The banner URL, when available.
        """
        banner = self.banner
        return banner.url if banner else None


@dataclass(slots=True)
class MutualGuild:
    """A guild both the caller and the profile's account are members of.

    Attributes:
        id: Guild ID.
        nick: The account's nickname in that guild, or None.
    """

    id: int
    nick: str | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> MutualGuild:
        """Build a MutualGuild from its decoded payload.

        Args:
            data: Mutual guild object.

        Returns:
            The parsed mutual guild.
        """
        return cls(id=int(data["id"]), nick=data.get("nick"))


@dataclass(slots=True)
class UserProfile:
    """Represents a Fluxer user's full profile.

    This contains profile information that is only available via the
    GET /users/{id}/profile endpoint, not from basic user objects.

    Attributes:
        user: The public representation of the target account.
        bio: The account-wide biography, or null when none is set.
        pronouns: The account-wide pronouns, or null when none are set.
        banner_hash: The image hash of the profile banner, or null when none is set.
        banner: The profile banner asset, or None.
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
    banner_hash: str | None = None
    banner_color: int | None = None
    accent_color: int | None = None

    # Premium information
    premium_type: int | None = None
    premium_since: str | None = None  # ISO 8601 timestamp
    premium_lifetime_sequence: int | None = None

    guild_member: GuildMember | None = None
    guild_member_profile: GuildMemberProfile | None = None
    timezone_offset: int | None = None
    profile_limited: bool | None = None
    mutual_friends: list[User] | None = None
    mutual_guilds: list[MutualGuild] | None = None
    connected_accounts: list[UserConnection] = field(default_factory=list)

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
            banner_hash=profile_data.get("banner"),
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
            guild_member_profile=GuildMemberProfile.from_data(
                data["guild_member_profile"],
                http,
                guild_id=guild_id,
                user_id=user.id,
            )
            if isinstance(data.get("guild_member_profile"), dict)
            else None,
            timezone_offset=data.get("timezone_offset"),
            profile_limited=data.get("profile_limited"),
            mutual_friends=[
                User.from_data(user, http) for user in data["mutual_friends"]
            ]
            if data.get("mutual_friends") is not None
            else None,
            mutual_guilds=[
                MutualGuild.from_data(item) for item in data["mutual_guilds"]
            ]
            if data.get("mutual_guilds") is not None
            else None,
            connected_accounts=[
                UserConnection.from_data(item, http)
                for item in data.get("connected_accounts", [])
            ],
            raw_data=dict(data),
            _http=http,
        )

    @property
    def banner(self) -> Asset | None:
        """The profile banner, or None when none is set.

        Returns:
            The banner asset, when set.
        """
        if self.banner_hash:
            return Asset._from_banner(self._http, self.user.id, self.banner_hash)
        return None

    @property
    def banner_url(self) -> str | None:
        """URL of :attr:`banner`, or None when none is set.

        Returns:
            The banner URL, when set.
        """
        banner = self.banner
        return banner.url if banner else None

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


__all__ = ("GuildMemberProfile", "MutualGuild", "UserProfile")
