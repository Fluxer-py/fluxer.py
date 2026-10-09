"""Member helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .._model_factory import _snapshot

from ..asset import Asset

from .._types import UNSET, UnsetType

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..file import File
    from ..http import HTTPClient
    from .channel import Channel
    from .message import Message

from .user import User


@dataclass(slots=True)
class GuildMember:
    """Represents a member of a guild.

    This combines a User object with guild-specific information like
    nickname, roles, join date, etc.

    A member can be used wherever a User is expected: account attributes
    (``username``, ``bot``, ``avatar_url``, ...) and ``send()``/``create_dm()``
    delegate to ``user``, and a member compares and hashes equal to the User
    with the same ID. Guild-specific profile values use ``guild_*`` names, and
    ``display_name``/``display_avatar`` prefer the guild value.

    Attributes:
        user: The account the membership belongs to.
        id: The account ID of this guild member.
        nick: The nickname the account uses in this guild, or null when none is set.
        guild_avatar_hash: Guild-specific avatar hash, or None when none is set.
        guild_banner_hash: Guild-specific banner hash, or None when none is set.
        guild_accent_color: The guild profile accent colour as packed 24-bit RGB, or null when none is set.
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
        guild_mention_flags: The reply mention preference that applies only inside this guild.
        display_name: Guild nickname, or the account's display name.
        display_avatar: Guild avatar, account avatar, or default avatar.
        display_avatar_url: URL of display_avatar.
        mention: Return a string that mentions this member.
        guild_avatar: The member's guild-specific avatar, if set.
        guild_avatar_url: URL for the member's guild-specific avatar, if set.
        guild_banner: The member's guild-specific banner, if set.
        guild_banner_url: URL for the member's guild-specific banner, if set.
    """

    # The underlying user
    user: User

    # Guild-specific fields
    nick: str | None = None  # Guild nickname (overrides global_name)
    guild_avatar_hash: str | None = None
    guild_banner_hash: str | None = None
    guild_accent_color: int | None = None
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
    guild_mention_flags: int | None = None

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
            guild_avatar_hash=data.get("avatar"),
            guild_banner_hash=data.get("banner"),
            guild_accent_color=data.get("accent_color"),
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
            guild_mention_flags=data.get("mention_flags", None),
            _http=http,
        )

    @property
    def id(self) -> int:
        """Return the ID of the account represented by this member.

        Returns:
            The member's account ID.
        """
        return self.user.id

    @property
    def display_name(self) -> str:
        """The best display name for this member.

        Priority: guild nickname > global name > username

        Returns:
            The result of this operation.
        """
        return self.nick or self.user.display_name

    @property
    def display_avatar(self) -> Asset:
        """The avatar shown for this member in the guild.

        The guild avatar takes precedence over the account avatar; a member with
        neither shows the account's default avatar.

        Returns:
            The guild, account, or default avatar asset.
        """
        return self.guild_avatar or self.user.display_avatar

    @property
    def display_avatar_url(self) -> str:
        """URL of :attr:`display_avatar`.

        Returns:
            The URL of the avatar shown for this member.
        """
        return self.display_avatar.url

    @property
    def mention(self) -> str:
        """Return a string that mentions this member.

        Returns:
            The result of this operation.
        """
        return f"<@{self.user.id}>"

    @property
    def guild_avatar(self) -> Asset | None:
        """The member's guild-specific avatar, or None when none is set.

        Returns:
            The guild avatar asset, when set.
        """
        if self.guild_avatar_hash:
            return Asset._from_guild_member_avatar(
                self._http, self.guild_id, self.user.id, self.guild_avatar_hash
            )
        return None

    @property
    def guild_avatar_url(self) -> str | None:
        """URL of :attr:`guild_avatar`, or None when none is set.

        Returns:
            The guild avatar URL, when set.
        """
        avatar = self.guild_avatar
        return avatar.url if avatar else None

    @property
    def guild_banner(self) -> Asset | None:
        """The member's guild-specific profile banner, or None when none is set.

        Returns:
            The guild banner asset, when set.
        """
        if self.guild_banner_hash:
            return Asset._from_guild_member_banner(
                self._http, self.guild_id, self.user.id, self.guild_banner_hash
            )
        return None

    @property
    def guild_banner_url(self) -> str | None:
        """URL of :attr:`guild_banner`, or None when none is set.

        Returns:
            The guild banner URL, when set.
        """
        banner = self.guild_banner
        return banner.url if banner else None

    # -- User delegation: lets a member stand in for its User --

    @property
    def username(self) -> str:
        """The account username (see :attr:`User.username`).

        Returns:
            The account username.
        """
        return self.user.username

    @property
    def discriminator(self) -> str | None:
        """The account discriminator (see :attr:`User.discriminator`).

        Returns:
            The account discriminator, when known.
        """
        return self.user.discriminator

    @property
    def global_name(self) -> str | None:
        """The account display name (see :attr:`User.global_name`).

        Returns:
            The account display name, when set.
        """
        return self.user.global_name

    @property
    def avatar_hash(self) -> str | None:
        """The account avatar hash; the guild avatar is :attr:`guild_avatar_hash`.

        Returns:
            The account avatar hash, when set.
        """
        return self.user.avatar_hash

    @property
    def avatar_color(self) -> int | None:
        """The account avatar colour (see :attr:`User.avatar_color`).

        Returns:
            The packed RGB colour, when known.
        """
        return self.user.avatar_color

    @property
    def banner_hash(self) -> str | None:
        """The account banner hash; the guild banner is :attr:`guild_banner_hash`.

        Returns:
            The account banner hash, when set.
        """
        return self.user.banner_hash

    @property
    def banner_color(self) -> int | None:
        """The account banner colour (see :attr:`User.banner_color`).

        Returns:
            The packed RGB colour, when known.
        """
        return self.user.banner_color

    @property
    def accent_color(self) -> int | None:
        """The account accent colour; the guild value is :attr:`guild_accent_color`.

        Returns:
            The packed RGB colour, when set.
        """
        return self.user.accent_color

    @property
    def mention_flags(self) -> int | None:
        """The account reply mention preference; see :attr:`guild_mention_flags`.

        Returns:
            The account-level preference, when set.
        """
        return self.user.mention_flags

    @property
    def bot(self) -> bool:
        """Whether the account is a bot (see :attr:`User.bot`).

        Returns:
            Whether the account is a bot.
        """
        return self.user.bot

    @property
    def system(self) -> bool:
        """Whether the account is a Fluxer system account (see :attr:`User.system`).

        Returns:
            Whether the account is a system account.
        """
        return self.user.system

    @property
    def flags(self) -> int:
        """Public account flags (see :attr:`User.flags`).

        Returns:
            The public flag mask.
        """
        return self.user.flags

    @property
    def bio(self) -> str | None:
        """The account biography (see :attr:`User.bio`).

        Returns:
            The biography, when known.
        """
        return self.user.bio

    @property
    def pronouns(self) -> str | None:
        """The account pronouns (see :attr:`User.pronouns`).

        Returns:
            The pronouns, when known.
        """
        return self.user.pronouns

    @property
    def created_at(self) -> datetime:
        """When the account was created (see :attr:`User.created_at`).

        Returns:
            The account creation time.
        """
        return self.user.created_at

    @property
    def avatar(self) -> Asset | None:
        """The account avatar; :attr:`guild_avatar` is the guild-specific one.

        Returns:
            The account avatar asset, when set.
        """
        return self.user.avatar

    @property
    def default_avatar(self) -> Asset:
        """The account's default avatar (see :attr:`User.default_avatar`).

        Returns:
            The default avatar asset.
        """
        return self.user.default_avatar

    @property
    def banner(self) -> Asset | None:
        """The account banner; :attr:`guild_banner` is the guild-specific one.

        Returns:
            The account banner asset, when set.
        """
        return self.user.banner

    @property
    def avatar_url(self) -> str | None:
        """The account avatar URL; :attr:`display_avatar` prefers the guild avatar.

        Returns:
            The account avatar URL, or None when the default avatar is used.
        """
        return self.user.avatar_url

    @property
    def default_avatar_url(self) -> str:
        """The account's default avatar URL (see :attr:`User.default_avatar_url`).

        Returns:
            The default avatar URL.
        """
        return self.user.default_avatar_url

    @property
    def banner_url(self) -> str | None:
        """The account banner URL (see :attr:`User.banner_url`).

        Returns:
            The account banner URL, when set.
        """
        return self.user.banner_url

    async def create_dm(self) -> Channel:
        """Open a DM channel with this member's account.

        Returns:
            The Channel object for the DM.
        """
        return await self.user.create_dm()

    async def send(
        self,
        content: str | None = None,
        *,
        embed: Any | None = None,
        embeds: list[Any] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        **kwargs: Any,
    ) -> Message:
        """Send a DM to this member's account.

        Args:
            content: The message content.
            embed: A single embed to include.
            embeds: Multiple embeds to include.
            file: A single File object to attach.
            files: Multiple File objects to attach.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The sent Message object.
        """
        return await self.user.send(
            content, embed=embed, embeds=embeds, file=file, files=files, **kwargs
        )

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
        """Edit this member and return an independent HTTP snapshot.

        The receiving member remains unchanged until a Gateway update arrives.

        Args:
            nick: New nickname (None to remove)
            roles: List of role IDs to set (replaces all roles)
            mute: Whether to mute in voice channels
            deaf: Whether to deafen in voice channels
            channel_id: Voice channel to move member to
            communication_disabled_until: Timeout timestamp (ISO 8601)
            reason: Reason for audit log

        Returns:
            Updated GuildMember snapshot with independent user and role data.
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
        updated = _snapshot(
            GuildMember.from_data,
            {"user": {"id": str(self.user.id)}, **data},
            self._http,
            guild_id=self.guild_id,
        )
        if "user" not in data:
            updated.user = deepcopy(self.user, {id(self._http): self._http})
        return updated

    def __eq__(self, other: object) -> bool:
        """Compare by account ID with another member or a User.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether both refer to the same account.
        """
        if isinstance(other, (GuildMember, User)):
            return self.id == other.id
        return NotImplemented

    def __hash__(self) -> int:
        """Hash by account ID, matching the equivalent User.

        Returns:
            The account ID hash.
        """
        return hash(self.id)

    def __str__(self) -> str:
        """Return the member's display name.

        Returns:
            The result of this operation.
        """
        return self.display_name


__all__ = ("GuildMember",)
