"""Typed responses for guild vanity URL, discovery, transfer and bulk operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from .._payload import maybe_int, unwrap

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class VanityUrl:
    """A Fluxer guild vanity URL response.

    Attributes:
        code: Stable server error code or invite identifier for this operation.
        uses: Uses used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    code: str | None = None
    uses: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> VanityUrl:
        """Build a VanityUrl from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed VanityUrl instance.
        """
        payload = unwrap(data, "vanity_url", "vanity")
        return cls(
            code=payload.get("code") or payload.get("vanity_url_code"),
            uses=maybe_int(payload.get("uses")),
            raw_data=data,
        )


_BulkResult = TypeVar("_BulkResult", bound="BulkOperationResult")


@dataclass(slots=True)
class BulkOperationResult:
    """A generic Fluxer bulk-operation response wrapper.

    Attributes:
        items: Successfully created expression payloads from the success array.
        failed: Failed used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    items: list[Any] = field(default_factory=list)
    failed: list[Any] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls: type[_BulkResult], data: dict[str, Any], http: HTTPClient | None = None
    ) -> _BulkResult:
        """Build a BulkOperationResult from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed BulkOperationResult instance.
        """
        return cls(
            items=list(data.get("success", [])),
            failed=list(data.get("failed", [])),
            raw_data=data,
        )


@dataclass(slots=True)
class DiscoveryApplication:
    """A Fluxer guild discovery application response.

    Attributes:
        guild_id: The ID of the guild.
        status: The application status of the listing.
        category_id: Identity of the category used by this operation.
        category_type: The discovery category the listing is filed under.
        description: The description shown on the listing.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        guild_nsfw_level: The NSFW level of the guild.
        primary_language: The supported primary language code of the listing, or null.
        custom_tags: The normalised custom tags of the listing.
        applied_at: The time at which the application was submitted.
        reviewed_at: The time at which the application was approved or rejected, or null.
        review_reason: The reason recorded with the approval or rejection, or null.
        removed_at: The time at which an approved listing was removed, or null.
        removal_reason: The reason recorded with the removal, or null.
    """

    guild_id: int | None = None
    status: str | None = None
    category_id: str | int | None = None
    category_type: int | None = None
    description: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    guild_nsfw_level: int | None = None
    primary_language: str | None = None
    custom_tags: list[str] | None = None
    applied_at: str | None = None
    reviewed_at: str | None = None
    review_reason: str | None = None
    removed_at: str | None = None
    removal_reason: str | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> DiscoveryApplication:
        """Build a DiscoveryApplication from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed DiscoveryApplication instance.
        """
        payload = unwrap(data, "application", "discovery_application")
        return cls(
            guild_id=maybe_int(payload.get("guild_id")),
            status=payload.get("status"),
            category_id=payload.get("category_type"),
            category_type=payload.get("category_type"),
            description=payload.get("description"),
            guild_nsfw_level=payload.get("guild_nsfw_level"),
            primary_language=payload.get("primary_language"),
            custom_tags=payload.get("custom_tags"),
            applied_at=payload.get("applied_at"),
            reviewed_at=payload.get("reviewed_at"),
            review_reason=payload.get("review_reason"),
            removed_at=payload.get("removed_at"),
            removal_reason=payload.get("removal_reason"),
            raw_data=data,
        )


@dataclass(slots=True)
class DiscoveryStatus:
    """A Fluxer guild discovery status response.

    Attributes:
        guild_id: Guild identity retained from the payload or operation context.
        status: Presence status accepted by the Fluxer Gateway.
        eligible: Whether the guild meets the requirement to apply.
        application: The current application of the guild, or null when it has never applied or has withdrawn.
        min_member_count: The number of members the instance requires.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    guild_id: int | None = None
    status: str | None = None
    eligible: bool | None = None
    application: DiscoveryApplication | None = None
    min_member_count: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> DiscoveryStatus:
        """Build a DiscoveryStatus from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed DiscoveryStatus instance.
        """
        payload = unwrap(data, "discovery", "status")
        app_data = payload.get("application") or payload.get("discovery_application")
        return cls(
            guild_id=maybe_int(payload.get("guild_id")),
            status=payload.get("status"),
            eligible=payload.get("eligible"),
            min_member_count=payload.get("min_member_count"),
            application=DiscoveryApplication.from_data(app_data, http)
            if isinstance(app_data, dict)
            else None,
            raw_data=data,
        )


@dataclass(slots=True)
class GuildTransferResult:
    """A Fluxer guild ownership transfer response.

    Attributes:
        guild_id: Guild identity retained from the payload or operation context.
        owner_id: Identity of the owning account when supplied by the object.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    guild_id: int | None = None
    owner_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> GuildTransferResult:
        """Build a GuildTransferResult from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed GuildTransferResult instance.
        """
        payload = unwrap(data, "guild")
        return cls(
            guild_id=maybe_int(payload.get("id") or payload.get("guild_id")),
            owner_id=maybe_int(payload.get("owner_id")),
            raw_data=data,
        )


class BulkEmojiResult(BulkOperationResult):
    """A bulk guild emoji creation response.

    Attributes:
        items: Successfully created expression payloads from the success array.
        failed: Failed used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """


class BulkStickerResult(BulkOperationResult):
    """A bulk guild sticker creation response.

    Attributes:
        items: Successfully created expression payloads from the success array.
        failed: Failed used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """


__all__ = (
    "VanityUrl",
    "BulkOperationResult",
    "DiscoveryApplication",
    "DiscoveryStatus",
    "GuildTransferResult",
    "BulkEmojiResult",
    "BulkStickerResult",
)
