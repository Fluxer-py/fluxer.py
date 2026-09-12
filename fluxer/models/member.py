"""Member helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .._endpoints import asset_url

from .._types import UNSET, UnsetType

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..http import HTTPClient

from .user import User


@dataclass(slots=True)
class GuildMember:
    """Represents a member of a guild.

    This combines a User object with guild-specific information like
    nickname, roles, join date, etc.

    Attributes:
        user: The account the membership belongs to.
        nick: The nickname the account uses in this guild, or null when none is set.
        avatar_hash: Avatar content hash, or None when no avatar is available.
        banner: The image hash of the guild-specific banner, or null when none is set.
        accent_color: The guild profile accent colour as packed 24-bit RGB, or null when none is set.
        roles: The IDs of the roles assigned to the membership (max 250).
        joined_at: The time the account became a member of this guild.
        guild_id: Guild identity retained from the payload or operation context.
        join_source_type: Join source type used by this operation.
        source_invite_code: Source invite code used by this operation.
        inviter_id: Identity of the inviter used by this operation.
        mute: Whether a moderator has muted the member in voice.
        deaf: Whether a moderator has deafened the member in voice.
        communication_disabled_until: The time the communication timeout expires, or null when the member is not timed out.
        profile_flags: The guild member profile flags set on the membership.
        mention_flags: The reply mention preference that applies only inside this guild.
        display_name: The best display name for this member.
        mention: Return a string that mentions this member.
        guild_avatar_url: URL for the member's guild-specific avatar, if set.
    """

    # The underlying user
    user: User

    # Guild-specific fields
    nick: str | None = None  # Guild nickname (overrides global_name)
    avatar_hash: str | None = None  # Guild-specific avatar hash
    banner: str | None = None  # Guild-specific banner
    accent_color: int | None = None  # Guild-specific accent color
    roles: list[int] = field(default_factory=list)  # Role IDs (as ints)
    joined_at: str | None = None  # ISO 8601 timestamp
    guild_id: int | None = None

    # Invite/join tracking
    join_source_type: int | None = None
    source_invite_code: str | None = None
    inviter_id: int | None = None

    # Voice state
    mute: bool = False
    deaf: bool = False

    # Moderation
    communication_disabled_until: str | None = None  # Timeout until (ISO 8601)

    # Back-reference (set after construction)
    profile_flags: int | None = None
    mention_flags: int | None = None

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        guild_id: int | None = None,
    ) -> GuildMember:
        # Parse the nested user object
        """Build a GuildMember from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.
            guild_id: Identity of the guild used by this operation.

        Returns:
            A parsed GuildMember instance.
        """
        user = User.from_data(data["user"], http)

        return cls(
            user=user,
            nick=data.get("nick"),
            avatar_hash=data.get("avatar"),
            banner=data.get("banner"),
            accent_color=data.get("accent_color"),
            roles=[int(role_id) for role_id in data.get("roles", [])],
            joined_at=data.get("joined_at"),
            join_source_type=data.get("join_source_type"),
            source_invite_code=data.get("source_invite_code"),
            inviter_id=int(data["inviter_id"]) if data.get("inviter_id") else None,
            mute=data.get("mute", False),
            deaf=data.get("deaf", False),
            communication_disabled_until=data.get("communication_disabled_until"),
            guild_id=guild_id
            or (int(data["guild_id"]) if data.get("guild_id") else None),
            profile_flags=data.get("profile_flags", None),
            mention_flags=data.get("mention_flags", None),
            _http=http,
        )

    @property
    def display_name(self) -> str:
        """The best display name for this member.

        Priority: guild nickname > global name > username

        Returns:
            The result of this operation.
        """
        return self.nick or self.user.global_name or self.user.username

    @property
    def mention(self) -> str:
        """Return a string that mentions this member.

        Returns:
            The result of this operation.
        """
        return f"<@{self.user.id}>"

    @property
    def guild_avatar_url(self) -> str | None:
        """URL for the member's guild-specific avatar, if set.

        Returns:
            The result of this operation.
        """
        if self.avatar_hash:
            ext = "gif" if self.avatar_hash.startswith("a_") else "png"
            # Note: Guild avatar URLs might have a different format
            # Adjust if Fluxer uses a different URL structure
            return asset_url(
                self._http,
                "media",
                f"guilds/{self.guild_id}/users/{self.user.id}/avatars/{self.avatar_hash}.{ext}",
            )
        return None

    # -- Role Management Methods --
    async def add_role(self, role_id: int, *, reason: str | None = None) -> None:
        """Add a role to this member.

        Args:
            role_id: Role ID to add
            reason: Reason for audit log

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot add role without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot add role without guild_id")

        await self._http.add_guild_member_role(
            self.guild_id, self.user.id, role_id, reason=reason
        )
        # Update local role list
        if role_id not in self.roles:
            self.roles.append(role_id)

    async def remove_role(self, role_id: int, *, reason: str | None = None) -> None:
        """Remove a role from this member.

        Args:
            role_id: Role ID to remove
            reason: Reason for audit log

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot remove role without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot remove role without guild_id")

        await self._http.remove_guild_member_role(
            self.guild_id, self.user.id, role_id, reason=reason
        )
        # Update local role list
        if role_id in self.roles:
            self.roles.remove(role_id)

    def has_role(self, role_id: int) -> bool:
        """Check if this member has a specific role.

        Args:
            role_id: Role ID to check

        Returns:
            True if member has the role, False otherwise
        """
        return role_id in self.roles

    # -- Moderation Methods --
    async def kick(self, *, reason: str | None = None) -> None:
        """Kick (remove) this member from the guild.

        Args:
            reason: Reason for audit log

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot kick member without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot kick member without guild_id")

        await self._http.kick_guild_member(self.guild_id, self.user.id, reason=reason)

    async def ban(
        self,
        *,
        delete_message_days: int = 0,
        delete_message_seconds: int = 0,
        reason: str | None = None,
    ) -> None:
        """Ban this member from the guild.

        Args:
            delete_message_days: Number of days to delete messages for (0-7)
            delete_message_seconds: Number of seconds to delete messages for (0-604800)
            reason: Reason for audit log

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot ban member without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot ban member without guild_id")

        await self._http.ban_guild_member(
            self.guild_id,
            self.user.id,
            delete_message_days=delete_message_days,
            delete_message_seconds=delete_message_seconds,
            reason=reason,
        )

    async def timeout(
        self, *, until: str | None = None, reason: str | None = None
    ) -> "GuildMember":
        """Timeout this member (or remove timeout).

        Args:
            until: ISO 8601 timestamp for when timeout expires (None to remove timeout)
            reason: Reason for audit log

        Returns:
            Updated GuildMember object
        """
        if not self._http:
            raise RuntimeError("Cannot timeout member without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot timeout member without guild_id")

        data = await self._http.timeout_guild_member(
            self.guild_id, self.user.id, until=until, reason=reason
        )
        # Update the local timeout field
        self.communication_disabled_until = data.get("communication_disabled_until")
        return self

    async def edit(
        self,
        *,
        nick: str | None | UnsetType = UNSET,
        roles: list[int | str] | None = None,
        mute: bool | None = None,
        deaf: bool | None = None,
        channel_id: int | None | UnsetType = UNSET,
        communication_disabled_until: str | None | UnsetType = UNSET,
        reason: str | None = None,
    ) -> "GuildMember":
        """Edit this member.

        Args:
            nick: New nickname (None to remove)
            roles: List of role IDs to set (replaces all roles)
            mute: Whether to mute in voice channels
            deaf: Whether to deafen in voice channels
            channel_id: Voice channel to move member to
            communication_disabled_until: Timeout timestamp (ISO 8601)
            reason: Reason for audit log

        Returns:
            Updated GuildMember object
        """
        if not self._http:
            raise RuntimeError("Cannot edit member without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot edit member without guild_id")

        data = await self._http.modify_guild_member(
            self.guild_id,
            self.user.id,
            nick=nick,
            roles=roles,
            mute=mute,
            deaf=deaf,
            channel_id=channel_id,
            communication_disabled_until=communication_disabled_until,
            reason=reason,
        )
        updated = GuildMember.from_data(
            {"user": {"id": str(self.user.id)}, **data},
            self._http,
            guild_id=self.guild_id,
        )
        if "user" not in data:
            updated.user = self.user
        for attribute in fields(self):
            setattr(self, attribute.name, getattr(updated, attribute.name))
        return self

    def __str__(self) -> str:
        """Return the member's display name.

        Returns:
            The result of this operation.
        """
        return self.display_name


__all__ = ("GuildMember",)
