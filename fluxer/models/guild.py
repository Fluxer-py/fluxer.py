"""Guild helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .._endpoints import asset_url

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .emoji import Emoji
from .member import GuildMember
from .role import Role
from ..sticker import Sticker

from ..utils import snowflake_to_datetime
from ..fluxer_models import (
    SearchAuthorType,
    SearchContentType,
    SearchEmbedType,
    SearchResponse,
    SearchSortBy,
    SearchSortOrder,
    parse_search_response,
)

if TYPE_CHECKING:
    from ..audit_logs import AuditLog
    from ..fluxer_models import BulkEmojiResult
    from ..fluxer_models import BulkStickerResult
    from ..fluxer_models import DiscoveryApplication
    from ..fluxer_models import DiscoveryStatus
    from ..fluxer_models import GuildTransferResult
    from ..fluxer_models import VanityUrl
    from ..invite import Invite
    from ..http import HTTPClient
    from .channel import Channel


@dataclass(slots=True)
class Guild:
    """Represents a Fluxer guild (server/community).

    Attributes:
        id: The ID of the guild.
        name: The name of the guild (1-100 characters).
        icon: Guild icon hash.
        owner_id: The ID of the guild owner.
        member_count: Member count held by the main Gateway.
        unavailable: Unavailable used by this operation.
        roles: Guild roles.
        channels: Guild channels the caller can view.
        members: Members used by this operation.
        emojis: Guild emojis.
        stickers: Guild stickers.
        banner: Guild banner hash.
        splash: Invite splash hash.
        embed_splash: Embedded invite splash hash.
        vanity_url_code: Custom invite code.
        message_history_cutoff: Earliest message visible to a member without `READ_MESSAGE_HISTORY`.
        content_warning_text: Guild content warning text (max 200 characters).
        banner_width: Banner width in pixels.
        banner_height: Banner height in pixels.
        splash_width: Invite splash width in pixels.
        splash_height: Invite splash height in pixels.
        embed_splash_width: Embedded invite splash width in pixels.
        embed_splash_height: Embedded invite splash height in pixels.
        online_count: Online presence count held by the main Gateway.
        approximate_member_count: Member count read from the main Gateway count cache.
        approximate_presence_count: Online presence count read from the main Gateway count cache.
        splash_card_alignment: Splash card alignment.
        system_channel_flags: System channel flags.
        afk_timeout: AFK timeout in seconds (60-3600).
        verification_level: Verification level.
        mfa_level: MFA level.
        nsfw_level: NSFW level.
        content_warning_level: Guild content warning level.
        explicit_content_filter: Guild explicit content filter level.
        default_message_notifications: Default message notification level.
        disabled_operations: Disabled guild operations.
        system_channel_id: Text channel that receives system messages.
        rules_channel_id: The ID of the rules channel.
        afk_channel_id: Voice channel that inactive members are moved to.
        permissions: Caller permissions in the guild.
        nsfw: Whether the guild is marked as adult content.
        features: Guild features.
        created_at: Return the UTC creation time encoded in this object's snowflake.
        icon_url: Build the guild icon URL from the discovered media service.
    """

    id: int
    name: str | None = None
    icon: str | None = None
    owner_id: int | None = None
    member_count: int | None = None
    unavailable: bool = False
    roles: list[Role] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    members: list[GuildMember] = field(default_factory=list)
    emojis: list[Emoji] = field(default_factory=list)
    stickers: list[Sticker] = field(default_factory=list)

    banner: str | None = None
    splash: str | None = None
    embed_splash: str | None = None
    vanity_url_code: str | None = None
    message_history_cutoff: str | None = None
    content_warning_text: str | None = None
    banner_width: int | None = None
    banner_height: int | None = None
    splash_width: int | None = None
    splash_height: int | None = None
    embed_splash_width: int | None = None
    embed_splash_height: int | None = None
    online_count: int | None = None
    approximate_member_count: int | None = None
    approximate_presence_count: int | None = None
    splash_card_alignment: int = 0
    system_channel_flags: int = 0
    afk_timeout: int = 0
    verification_level: int = 0
    mfa_level: int = 0
    nsfw_level: int = 0
    content_warning_level: int = 0
    explicit_content_filter: int = 0
    default_message_notifications: int = 0
    disabled_operations: int = 0
    system_channel_id: int | None = None
    rules_channel_id: int | None = None
    afk_channel_id: int | None = None
    permissions: int | None = None
    nsfw: bool = False
    features: list[str] = field(default_factory=list)

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Guild:
        """Build a Guild from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Guild instance.
        """
        from .channel import Channel

        data = {**data.get("properties", {}), **data}
        guild_id = int(data["id"])
        guild = cls(
            id=int(data["id"]),
            name=data.get("name"),
            icon=data.get("icon"),
            owner_id=int(data["owner_id"]) if data.get("owner_id") else None,
            member_count=data.get("member_count"),
            unavailable=data.get("unavailable", False),
            roles=[
                Role.from_data(role, http, guild_id) for role in data.get("roles", [])
            ],
            channels=[
                Channel.from_data({**channel, "guild_id": str(guild_id)}, http)
                for channel in data.get("channels", [])
            ],
            members=[
                GuildMember.from_data(member, http, guild_id=guild_id)
                for member in data.get("members", [])
            ],
            emojis=[
                Emoji.from_data(emoji, http, guild_id=guild_id)
                for emoji in data.get("emojis", [])
            ],
            stickers=[
                Sticker.from_data(sticker, http, guild_id=guild_id)
                for sticker in data.get("stickers", [])
            ],
            banner=data.get("banner", None),
            splash=data.get("splash", None),
            embed_splash=data.get("embed_splash", None),
            vanity_url_code=data.get("vanity_url_code", None),
            message_history_cutoff=data.get("message_history_cutoff", None),
            content_warning_text=data.get("content_warning_text", None),
            banner_width=data.get("banner_width", None),
            banner_height=data.get("banner_height", None),
            splash_width=data.get("splash_width", None),
            splash_height=data.get("splash_height", None),
            embed_splash_width=data.get("embed_splash_width", None),
            embed_splash_height=data.get("embed_splash_height", None),
            online_count=data.get("online_count", None),
            approximate_member_count=data.get("approximate_member_count", None),
            approximate_presence_count=data.get("approximate_presence_count", None),
            splash_card_alignment=data.get("splash_card_alignment", 0),
            system_channel_flags=data.get("system_channel_flags", 0),
            afk_timeout=data.get("afk_timeout", 0),
            verification_level=data.get("verification_level", 0),
            mfa_level=data.get("mfa_level", 0),
            nsfw_level=data.get("nsfw_level", 0),
            content_warning_level=data.get("content_warning_level", 0),
            explicit_content_filter=data.get("explicit_content_filter", 0),
            default_message_notifications=data.get("default_message_notifications", 0),
            disabled_operations=data.get("disabled_operations", 0),
            system_channel_id=int(data["system_channel_id"])
            if data.get("system_channel_id") is not None
            else None,
            rules_channel_id=int(data["rules_channel_id"])
            if data.get("rules_channel_id") is not None
            else None,
            afk_channel_id=int(data["afk_channel_id"])
            if data.get("afk_channel_id") is not None
            else None,
            permissions=int(data["permissions"])
            if data.get("permissions") is not None
            else None,
            nsfw=data.get("nsfw", False),
            features=list(data.get("features", [])),
            _http=http,
        )

        for channel in guild.channels:
            channel._guild = guild
        return guild

    @property
    def created_at(self) -> datetime:
        """Return the UTC creation time encoded in this object's snowflake.

        Returns:
            The result of this operation.
        """
        return snowflake_to_datetime(self.id)

    @property
    def icon_url(self) -> str | None:
        """Build the guild icon URL from the discovered media service.

        Returns:
            The result of this operation.
        """
        if self.icon:
            ext = "gif" if self.icon.startswith("a_") else "png"
            return asset_url(self._http, "media", f"icons/{self.id}/{self.icon}.{ext}")
        return None

    async def fetch_emojis(self) -> list[Emoji]:
        """Fetch all emojis in this guild.

        Returns:
            List of Emoji objects
        """
        if not self._http:
            raise RuntimeError("Cannot fetch emojis without HTTPClient")

        from .emoji import Emoji

        data = await self._http.get_guild_emojis(self.id)
        # Pass guild_id when creating emojis since API doesn't always return it
        return [
            Emoji.from_data(emoji_data, self._http, guild_id=self.id)
            for emoji_data in data
        ]

    # -- Role Management Methods --
    async def fetch_roles(self) -> list[Role]:
        """Fetch all roles in this guild.

        Returns:
            List of Role objects
        """
        if not self._http:
            raise RuntimeError("Cannot fetch roles without HTTPClient")

        from .role import Role

        data = await self._http.get_guild_roles(self.id)
        return [
            Role.from_data(role_data, self._http, guild_id=self.id)
            for role_data in data
        ]

    async def create_role(
        self,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int = 0,
        hoist: bool = False,
        mentionable: bool = False,
    ) -> Role:
        """Create a new role in this guild.

        Args:
            name: Role name
            permissions: Permission bitfield
            color: Role color
            hoist: Whether to display role separately
            mentionable: Whether role can be mentioned

        Returns:
            Role object
        """
        if not self._http:
            raise RuntimeError("Cannot create role without HTTPClient")

        from .role import Role

        data = await self._http.create_guild_role(
            self.id,
            name=name,
            permissions=permissions,
            color=color,
            hoist=hoist,
            mentionable=mentionable,
        )
        return Role.from_data(data, self._http, guild_id=self.id)

    # -- Member Management Methods --
    async def fetch_member(self, user_id: int) -> GuildMember:
        """Fetch a specific member from this guild.

        Args:
            user_id: User ID to fetch

        Returns:
            GuildMember object
        """
        if not self._http:
            raise RuntimeError("Cannot fetch member without HTTPClient")

        from .member import GuildMember

        data = await self._http.get_guild_member(self.id, user_id)
        return GuildMember.from_data(data, self._http, guild_id=self.id)

    async def fetch_members(
        self, *, limit: int = 100, after: int | None = None
    ) -> list[GuildMember]:
        """Fetch members from this guild.

        Args:
            limit: Maximum number of members to fetch (1-1000)
            after: Fetch members after this user ID

        Returns:
            List of GuildMember objects
        """
        if not self._http:
            raise RuntimeError("Cannot fetch members without HTTPClient")

        from .member import GuildMember

        data = await self._http.get_guild_members(self.id, limit=limit, after=after)
        return [
            GuildMember.from_data(member_data, self._http, guild_id=self.id)
            for member_data in data
        ]

    # -- Moderation Methods --
    async def kick(self, user_id: int, *, reason: str | None = None) -> None:
        """Kick a member from this guild.

        Args:
            user_id: User ID to kick
            reason: Reason for audit log

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot kick member without HTTPClient")

        await self._http.kick_guild_member(self.id, user_id, reason=reason)

    async def ban(
        self,
        user_id: int,
        *,
        ban_duration_seconds: int = 0,
        delete_message_days: int = 0,
        delete_message_seconds: int = 0,
        reason: str | None = None,
    ) -> None:
        """Ban a user from this guild.

        Args:
            user_id: User ID to ban
            ban_duration_seconds: Duration of the ban in seconds (0 for permanent, or a valid temporary duration)
            delete_message_days: Number of days to delete messages for (0-7)
            delete_message_seconds: Number of seconds to delete messages for (0-604800)
            reason: Reason for audit log

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot ban member without HTTPClient")

        await self._http.ban_guild_member(
            self.id,
            user_id,
            ban_duration_seconds=ban_duration_seconds,
            delete_message_days=delete_message_days,
            delete_message_seconds=delete_message_seconds,
            reason=reason,
        )

    async def unban(self, user_id: int, *, reason: str | None = None) -> None:
        """Unban a user from this guild.

        Args:
            user_id: User ID to unban
            reason: Reason for audit log

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot unban user without HTTPClient")

        await self._http.unban_guild_member(self.id, user_id, reason=reason)

    async def invites(self) -> list[Invite]:
        """Fetch invites for this guild.

        Returns:
            The result of this operation.
        """
        from ..invite import Invite

        if not self._http:
            raise RuntimeError("Cannot fetch invites without HTTPClient")
        data = await self._http.get_guild_invites(self.id)
        return [Invite.from_data(item, self._http) for item in data]

    async def audit_logs(self, **kwargs: Any) -> AuditLog:
        """Fetch this guild's audit log.

        Args:
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        from ..audit_logs import AuditLog

        if not self._http:
            raise RuntimeError("Cannot fetch audit logs without HTTPClient")
        data = await self._http.get_guild_audit_logs(self.id, **kwargs)
        return AuditLog.from_data(data)

    async def fetch_stickers(self) -> list[Sticker]:
        """Fetch all stickers in this guild.

        Returns:
            The requested stickers.
        """
        if not self._http:
            raise RuntimeError("Cannot fetch stickers without HTTPClient")
        data = await self._http.get_guild_stickers(self.id)
        return [Sticker.from_data(item, self._http, guild_id=self.id) for item in data]

    async def discovery_status(self) -> DiscoveryStatus:
        """Discovery status.

        Returns:
            The result of this operation.
        """
        from ..fluxer_models import DiscoveryStatus

        if not self._http:
            raise RuntimeError("Cannot fetch discovery status without HTTPClient")
        return DiscoveryStatus.from_data(
            await self._http.get_guild_discovery_status(self.id), self._http
        )

    async def apply_for_discovery(self, **payload: Any) -> DiscoveryApplication:
        """Apply for discovery.

        Args:
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        from ..fluxer_models import DiscoveryApplication

        if not self._http:
            raise RuntimeError("Cannot apply for discovery without HTTPClient")
        method = getattr(self._http, "apply_for_guild_discovery", None)
        if method is None:
            method = self._http.apply_for_discovery
        return DiscoveryApplication.from_data(
            await method(self.id, **payload), self._http
        )

    async def edit_discovery_application(self, **payload: Any) -> DiscoveryApplication:
        """Edit discovery application.

        Args:
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        from ..fluxer_models import DiscoveryApplication

        if not self._http:
            raise RuntimeError("Cannot edit discovery application without HTTPClient")
        method = getattr(self._http, "edit_guild_discovery_application", None)
        if method is None:
            method = self._http.edit_discovery_application
        return DiscoveryApplication.from_data(
            await method(self.id, **payload),
            self._http,
        )

    async def withdraw_discovery_application(self) -> None:
        """Withdraw discovery application.

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError(
                "Cannot withdraw discovery application without HTTPClient"
            )
        await self._http.withdraw_discovery_application(self.id)

    async def join_discovery(self) -> None:
        """Join discovery.

        Returns:
            The result of this operation.
        """
        if not self._http:
            raise RuntimeError("Cannot join discovery guild without HTTPClient")
        return await self._http.join_discovery_guild(self.id)

    async def get_vanity_url(self) -> VanityUrl:
        """Get vanity url.

        Returns:
            The requested vanity url.
        """
        from ..fluxer_models import VanityUrl

        if not self._http:
            raise RuntimeError("Cannot fetch vanity URL without HTTPClient")
        return VanityUrl.from_data(
            await self._http.get_guild_vanity_url(self.id), self._http
        )

    async def update_vanity_url(self, code: str) -> VanityUrl:
        """Update vanity url.

        Args:
            code: Stable server error code or invite identifier for this operation.

        Returns:
            The result of this operation.
        """
        from ..fluxer_models import VanityUrl

        if not self._http:
            raise RuntimeError("Cannot update vanity URL without HTTPClient")
        return VanityUrl.from_data(
            await self._http.update_guild_vanity_url(self.id, code), self._http
        )

    async def transfer_ownership(
        self, new_owner_id: int | str, **payload: Any
    ) -> GuildTransferResult:
        """Transfer ownership.

        Args:
            new_owner_id: Identity of the new owner used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        from ..fluxer_models import GuildTransferResult

        if not self._http:
            raise RuntimeError("Cannot transfer ownership without HTTPClient")
        return GuildTransferResult.from_data(
            await self._http.transfer_guild_ownership(self.id, new_owner_id, **payload),
            self._http,
        )

    async def bulk_create_emojis(self, emojis: list[dict[str, Any]]) -> BulkEmojiResult:
        """Bulk create emojis.

        Args:
            emojis: Emojis used by this operation.

        Returns:
            The result of this operation.
        """
        from ..fluxer_models import BulkEmojiResult

        if not self._http:
            raise RuntimeError("Cannot create emojis without HTTPClient")
        return BulkEmojiResult.from_data(
            await self._http.bulk_create_guild_emojis(self.id, emojis), self._http
        )

    async def bulk_create_stickers(
        self, stickers: list[dict[str, Any]]
    ) -> BulkStickerResult:
        """Bulk create stickers.

        Args:
            stickers: Stickers used by this operation.

        Returns:
            The result of this operation.
        """
        from ..fluxer_models import BulkStickerResult

        if not self._http:
            raise RuntimeError("Cannot create stickers without HTTPClient")
        return BulkStickerResult.from_data(
            await self._http.bulk_create_guild_stickers(self.id, stickers), self._http
        )

    async def clone_emoji(self, **payload: Any) -> Emoji:
        """Clone emoji.

        Args:
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        if not self._http:
            raise RuntimeError("Cannot clone emoji without HTTPClient")
        data = await self._http.clone_guild_emoji(self.id, **payload)
        return Emoji.from_data(data, self._http, guild_id=self.id)

    async def clone_sticker(self, **payload: Any) -> Sticker:
        """Clone sticker.

        Args:
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        if not self._http:
            raise RuntimeError("Cannot clone sticker without HTTPClient")
        data = await self._http.clone_guild_sticker(self.id, **payload)
        return Sticker.from_data(data, self._http, guild_id=self.id)

    async def search_messages(
        self,
        *,
        channel_ids: list[int | str] | None = None,
        channel_id: list[int | str] | None = None,
        hits_per_page: int | None = None,
        page: int | None = None,
        cursor: list[str] | None = None,
        min_id: int | str | None = None,
        max_id: int | str | None = None,
        content: str | None = None,
        contents: list[str] | None = None,
        exact_phrases: list[str] | None = None,
        exclude_channel_id: list[int | str] | None = None,
        author_id: list[int | str] | None = None,
        exclude_author_id: list[int | str] | None = None,
        author_type: list[SearchAuthorType] | None = None,
        exclude_author_type: list[SearchAuthorType] | None = None,
        mentions: list[int | str] | None = None,
        exclude_mentions: list[int | str] | None = None,
        mention_everyone: bool | None = None,
        pinned: bool | None = None,
        has: list[SearchContentType] | None = None,
        exclude_has: list[SearchContentType] | None = None,
        embed_type: list[SearchEmbedType] | None = None,
        exclude_embed_type: list[SearchEmbedType] | None = None,
        embed_provider: list[str] | None = None,
        exclude_embed_provider: list[str] | None = None,
        link_hostname: list[str] | None = None,
        exclude_link_hostname: list[str] | None = None,
        attachment_filename: list[str] | None = None,
        exclude_attachment_filename: list[str] | None = None,
        attachment_extension: list[str] | None = None,
        exclude_attachment_extension: list[str] | None = None,
        sort_by: SearchSortBy | None = None,
        sort_order: SearchSortOrder | None = None,
        include_nsfw: bool | None = None,
    ) -> SearchResponse:
        """Search messages in this guild using Fluxer's bot-safe current scope.

        Args:
            channel_ids: IDs of the channel resources selected by this operation.
            channel_id: Identity of the channel used by this operation.
            hits_per_page: Maximum search hits requested in one result page.
            page: Page number passed to the search operation.
            cursor: Opaque search continuation values from the preceding result.
            min_id: Lower message-ID bound for search results.
            max_id: Upper message-ID bound for search results.
            content: Text content sent in the message.
            contents: Contents used by this operation.
            exact_phrases: Exact phrases used by this operation.
            exclude_channel_id: Identity of the exclude channel used by this operation.
            author_id: Identity of the author used by this operation.
            exclude_author_id: Identity of the exclude author used by this operation.
            author_type: Author type used by this operation.
            exclude_author_type: Author type values excluded from search results.
            mentions: Mentions used by this operation.
            exclude_mentions: Mentions values excluded from search results.
            mention_everyone: Mention everyone used by this operation.
            pinned: Pinned used by this operation.
            has: Has used by this operation.
            exclude_has: Has values excluded from search results.
            embed_type: Embed type used by this operation.
            exclude_embed_type: Embed type values excluded from search results.
            embed_provider: Embed provider used by this operation.
            exclude_embed_provider: Embed provider values excluded from search results.
            link_hostname: Link hostname used by this operation.
            exclude_link_hostname: Link hostname values excluded from search results.
            attachment_filename: Attachment filename used by this operation.
            exclude_attachment_filename: Attachment filename values excluded from search results.
            attachment_extension: Attachment extension used by this operation.
            exclude_attachment_extension: Attachment extension values excluded from search results.
            sort_by: Sort by used by this operation.
            sort_order: Sort order used by this operation.
            include_nsfw: Whether the search may include mature content accessible to the caller.

        Returns:
            The result of this operation.
        """
        if not self._http:
            raise RuntimeError("Cannot search messages without HTTPClient")
        data = await self._http.search_messages(
            scope="current",
            context_guild_id=self.id,
            channel_ids=channel_ids,
            channel_id=channel_id,
            hits_per_page=hits_per_page,
            page=page,
            cursor=cursor,
            min_id=min_id,
            max_id=max_id,
            content=content,
            contents=contents,
            exact_phrases=exact_phrases,
            exclude_channel_id=exclude_channel_id,
            author_id=author_id,
            exclude_author_id=exclude_author_id,
            author_type=author_type,
            exclude_author_type=exclude_author_type,
            mentions=mentions,
            exclude_mentions=exclude_mentions,
            mention_everyone=mention_everyone,
            pinned=pinned,
            has=has,
            exclude_has=exclude_has,
            embed_type=embed_type,
            exclude_embed_type=exclude_embed_type,
            embed_provider=embed_provider,
            exclude_embed_provider=exclude_embed_provider,
            link_hostname=link_hostname,
            exclude_link_hostname=exclude_link_hostname,
            attachment_filename=attachment_filename,
            exclude_attachment_filename=exclude_attachment_filename,
            attachment_extension=attachment_extension,
            exclude_attachment_extension=exclude_attachment_extension,
            sort_by=sort_by,
            sort_order=sort_order,
            include_nsfw=include_nsfw,
        )
        return parse_search_response(data, self._http)

    def __str__(self) -> str:
        """Return the object's user-facing text representation.

        Returns:
            The result of this operation.
        """
        return self.name or f"Guild({self.id})"


__all__ = ("Guild",)
