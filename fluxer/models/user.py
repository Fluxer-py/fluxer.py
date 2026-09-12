"""User helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .._endpoints import asset_url

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..file import File
    from ..http import HTTPClient
    from .channel import Channel
    from .message import Message


@dataclass(slots=True)
class User:
    """A complete or partial Fluxer user payload.

    ID-only references have an empty username until resolved from cached user data.
    Private fields may be absent or null; raw_data retains that distinction.

    Attributes:
        id: The snowflake that identifies the account.
        username: The account username (1-32 ASCII letters, digits, or underscores).
        discriminator: The account discriminator, four decimal digits with leading zeroes.
        global_name: The display name of the account, or null when none is set.
        avatar_hash: Avatar content hash, or None when no avatar is available.
        avatar_color: The packed 24-bit RGB colour derived from the stored avatar, or null.
        bot: Whether the account is a bot, omitted when false.
        flags: Public user flags.
        bio: The profile biography, or null when none is set.
        banner_hash: Banner content hash, or None when no banner is available.
        banner_color: The packed 24-bit RGB colour derived from the stored banner, or null.
        system: Whether the account is a Fluxer system account, omitted when false.
        mention_flags: Reply mention preference, omitted when the account has no preference.
        pronouns: The profile pronouns, or null when none are set.
        accent_color: The profile accent colour as packed 24-bit RGB, or null when none is set.
        is_staff: Whether the account has the staff flag, including when that flag is hidden from `flags`.
        email_bounced: Whether the mail provider marked the current email as bounced.
        has_verified_phone: Whether phone verification is complete.
        mfa_enabled: Whether any authenticator is configured.
        verified: Whether the account email is verified.
        premium_will_cancel: Whether subscription premium will cancel at the billing boundary.
        premium_discriminator: Whether the current discriminator was selected under a premium entitlement.
        nsfw_allowed: Whether the account can access age-restricted content.
        has_dismissed_premium_onboarding: Whether premium onboarding was dismissed.
        has_ever_purchased: Whether the account has completed a purchase.
        has_unread_gift_inventory: Whether the gift inventory has unread items.
        age_verified_adult: Whether adult age verification is complete, omitted when false.
        force_inbound_phone_verification: The debugging switch that forces the inbound phone verification flow.
        email: The account email address, or null when none exists.
        phone: Always null.
        timezone: The IANA timezone identifier stored for the account, or null when none is set.
        premium_since: The time premium was first activated, or null.
        premium_until: The end of current premium access, or null when no premium period is stored.
        premium_billing_cycle: The premium billing cycle, or null.
        premium_grace_ends_at: The end of the post-cancellation grace interval, or null when the account is not in grace.
        password_last_changed_at: The time of the most recent password change, or null.
        last_voice_activity_sharing_change_at: The time of the most recent bulk voice activity sharing change, or null.
        terms_agreed_at: The time of the most recent terms acceptance, or null.
        privacy_agreed_at: The time of the most recent privacy policy acceptance, or null.
        premium_type: Premium type.
        premium_lifetime_sequence: The lifetime premium sequence, or null.
        timezone_privacy_flags: Profile field privacy flags applied to the profile timezone.
        unread_gift_inventory_count: The number of unread gift inventory items.
        acls: The Admin access control entries held by the account.
        traits: The account traits, in sorted order.
        required_actions: The ordered required actions the account must complete before unrestricted use.
        authenticator_types: Authenticator types configured for the account.
        pending_bulk_message_deletion: The message deletion the account scheduled for itself, or null when none is pending.
        premium_badge_hidden: Whether the premium badge is hidden from the public profile.
        premium_badge_masked: Whether a lifetime badge is presented as an ordinary subscription badge.
        premium_badge_timestamp_hidden: Whether the premium activation time is hidden from the public profile.
        premium_badge_sequence_hidden: Whether the lifetime sequence is hidden from the public profile.
        premium_purchase_disabled: Whether premium purchasing is disabled for the account.
        premium_enabled_override: Whether an administrative override grants premium entitlements.
        premium_perks_disabled: Whether premium entitlements are suspended for the account.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        created_at: When this user account was created (derived from Snowflake).
        display_name: The best display name for this user.
        mention: Return a string that mentions this user in a message.
        avatar_url: URL for the user's avatar, or None if they use the default.
        default_avatar_url: URL for the user's default avatar.
        banner_url: URL for the user's banner, or None if they don't have one.
    """

    # Core identity fields (available everywhere)
    id: int
    username: str = ""
    discriminator: str | None = None
    global_name: str | None = None  # Display name/nickname
    avatar_hash: str | None = None
    avatar_color: int | None = None
    bot: bool = False
    flags: int = 0

    # Additional profile fields (may not be available for all users)
    bio: str | None = None  # User bio/about me
    banner_hash: str | None = None  # Banner image hash
    banner_color: int | None = None  # Banner color (integer)

    # Back-reference (set after construction)
    system: bool = False
    mention_flags: int | None = None
    pronouns: str | None = None
    accent_color: int | None = None
    is_staff: bool | None = None
    email_bounced: bool | None = None
    has_verified_phone: bool | None = None
    mfa_enabled: bool | None = None
    verified: bool | None = None
    premium_will_cancel: bool | None = None
    premium_discriminator: bool | None = None
    nsfw_allowed: bool | None = None
    has_dismissed_premium_onboarding: bool | None = None
    has_ever_purchased: bool | None = None
    has_unread_gift_inventory: bool | None = None
    age_verified_adult: bool | None = None
    force_inbound_phone_verification: bool | None = None
    email: str | None = None
    phone: str | None = None
    timezone: str | None = None
    premium_since: str | None = None
    premium_until: str | None = None
    premium_billing_cycle: str | None = None
    premium_grace_ends_at: str | None = None
    password_last_changed_at: str | None = None
    last_voice_activity_sharing_change_at: str | None = None
    terms_agreed_at: str | None = None
    privacy_agreed_at: str | None = None
    premium_type: int | None = None
    premium_lifetime_sequence: int | None = None
    timezone_privacy_flags: int | None = None
    unread_gift_inventory_count: int | None = None
    acls: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    authenticator_types: list[int] = field(default_factory=list)
    pending_bulk_message_deletion: dict[str, Any] | None = None

    _http: HTTPClient | None = field(default=None, repr=False)

    premium_badge_hidden: bool | None = None
    premium_badge_masked: bool | None = None
    premium_badge_timestamp_hidden: bool | None = None
    premium_badge_sequence_hidden: bool | None = None
    premium_purchase_disabled: bool | None = None
    premium_enabled_override: bool | None = None
    premium_perks_disabled: bool | None = None

    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> User:
        """Build a User from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed User instance.
        """
        return cls(
            id=int(data["id"]),
            username=data.get("username", ""),
            discriminator=data.get("discriminator"),
            global_name=data.get("global_name"),
            avatar_hash=data.get("avatar"),
            avatar_color=data.get("avatar_color"),
            bot=data.get("bot", False),
            flags=data.get("flags", 0),
            bio=data.get("bio"),
            banner_hash=data.get("banner"),
            banner_color=data.get("banner_color"),
            system=data.get("system", False),
            mention_flags=data.get("mention_flags", None),
            pronouns=data.get("pronouns", None),
            accent_color=data.get("accent_color", None),
            is_staff=data.get("is_staff", None),
            email_bounced=data.get("email_bounced", None),
            has_verified_phone=data.get("has_verified_phone", None),
            mfa_enabled=data.get("mfa_enabled", None),
            verified=data.get("verified", None),
            premium_will_cancel=data.get("premium_will_cancel", None),
            premium_discriminator=data.get("premium_discriminator", None),
            nsfw_allowed=data.get("nsfw_allowed", None),
            has_dismissed_premium_onboarding=data.get(
                "has_dismissed_premium_onboarding", None
            ),
            has_ever_purchased=data.get("has_ever_purchased", None),
            has_unread_gift_inventory=data.get("has_unread_gift_inventory", None),
            age_verified_adult=data.get("age_verified_adult", None),
            force_inbound_phone_verification=data.get(
                "force_inbound_phone_verification", None
            ),
            email=data.get("email", None),
            phone=data.get("phone", None),
            timezone=data.get("timezone", None),
            premium_since=data.get("premium_since", None),
            premium_until=data.get("premium_until", None),
            premium_billing_cycle=data.get("premium_billing_cycle", None),
            premium_grace_ends_at=data.get("premium_grace_ends_at", None),
            password_last_changed_at=data.get("password_last_changed_at", None),
            last_voice_activity_sharing_change_at=data.get(
                "last_voice_activity_sharing_change_at", None
            ),
            terms_agreed_at=data.get("terms_agreed_at", None),
            privacy_agreed_at=data.get("privacy_agreed_at", None),
            premium_type=data.get("premium_type", None),
            premium_lifetime_sequence=data.get("premium_lifetime_sequence", None),
            timezone_privacy_flags=data.get("timezone_privacy_flags", None),
            unread_gift_inventory_count=data.get("unread_gift_inventory_count", None),
            acls=list(data.get("acls", [])),
            traits=list(data.get("traits", [])),
            required_actions=list(data.get("required_actions", [])),
            authenticator_types=list(data.get("authenticator_types", [])),
            pending_bulk_message_deletion=data.get(
                "pending_bulk_message_deletion", None
            ),
            premium_badge_hidden=data.get("premium_badge_hidden"),
            premium_badge_masked=data.get("premium_badge_masked"),
            premium_badge_timestamp_hidden=data.get("premium_badge_timestamp_hidden"),
            premium_badge_sequence_hidden=data.get("premium_badge_sequence_hidden"),
            premium_purchase_disabled=data.get("premium_purchase_disabled"),
            premium_enabled_override=data.get("premium_enabled_override"),
            premium_perks_disabled=data.get("premium_perks_disabled"),
            raw_data=dict(data),
            _http=http,
        )

    @property
    def created_at(self) -> datetime:
        """When this user account was created (derived from Snowflake).

        Returns:
            The result of this operation.
        """
        return snowflake_to_datetime(self.id)

    @property
    def display_name(self) -> str:
        """The best display name for this user.

        Returns global_name if set, otherwise falls back to username.
        This is the name you should show to users.

        Returns:
            The result of this operation.
        """
        return self.global_name or self.username

    @property
    def mention(self) -> str:
        """Return a string that mentions this user in a message.

        Returns:
            The result of this operation.
        """
        return f"<@{self.id}>"

    @property
    def avatar_url(self) -> str | None:
        """URL for the user's avatar, or None if they use the default.

        Returns:
            The result of this operation.
        """
        if self.avatar_hash:
            ext = "gif" if self.avatar_hash.startswith("a_") else "png"
            return asset_url(
                self._http, "media", f"avatars/{self.id}/{self.avatar_hash}.{ext}"
            )
        return None

    @property
    def default_avatar_url(self) -> str:
        """URL for the user's default avatar.

        Returns:
            The result of this operation.
        """
        index = int(self.id) % 6
        return asset_url(self._http, "static_cdn", f"avatars/{index}.png")

    @property
    def banner_url(self) -> str | None:
        """URL for the user's banner, or None if they don't have one.

        Returns:
            The result of this operation.
        """
        if self.banner_hash:
            ext = "gif" if self.banner_hash.startswith("a_") else "png"
            return asset_url(
                self._http, "media", f"banners/{self.id}/{self.banner_hash}.{ext}"
            )
        return None

    async def create_dm(self) -> Channel:
        """Open a DM channel with this user.

        Returns the existing DM channel if one is already open.

        Returns:
            The Channel object for the DM.
        """
        from .channel import Channel

        if self._http is None:
            raise RuntimeError("User is not bound to an HTTP client")
        data = await self._http.create_dm(self.id)
        return Channel.from_data(data, self._http)

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
        """Send a DM to this user.

        Opens a DM channel, then sends the message.

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
        channel = await self.create_dm()
        return await channel.send(
            content, embed=embed, embeds=embeds, file=file, files=files, **kwargs
        )

    def __eq__(self, other: object) -> bool:
        """Compare this object with another value using its identity semantics.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return isinstance(other, User) and self.id == other.id

    def __hash__(self) -> int:
        """Return the hash used for identity-based collection lookup.

        Returns:
            The result of this operation.
        """
        return hash(self.id)

    def __str__(self) -> str:
        """Return the user's display name.

        Uses global_name if available, otherwise username.

        Returns:
            The result of this operation.
        """
        return self.global_name or self.username


__all__ = ("User",)
