"""Typed views of existing Fluxer response payloads and compatibility containers.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypeVar

if TYPE_CHECKING:
    from .models import Channel, Message, User
    from .http import HTTPClient


SearchScope: TypeAlias = Literal[
    "current",
    "open_dms",
    "all_dms",
    "all_guilds",
    "all",
    "open_dms_and_all_guilds",
]
SearchAuthorType: TypeAlias = Literal["user", "bot", "webhook"]
SearchContentType: TypeAlias = Literal[
    "image", "sound", "video", "file", "sticker", "embed", "link", "poll", "snapshot"
]
SearchEmbedType: TypeAlias = Literal["image", "video", "sound", "article"]
SearchSortBy: TypeAlias = Literal["timestamp", "relevance"]
SearchSortOrder: TypeAlias = Literal["asc", "desc"]


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unwrap(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


@dataclass(slots=True)
class AttachmentUploadSpec:
    """Fluxer attachment upload specification for the presigned upload route.

    Attributes:
        id: Identity of the object used by this operation.
        filename: Filename presented to the server and recipients.
        file_size: Exact file length in bytes declared when planning the upload.
        content_type: Content type used by this operation.
    """

    id: int
    filename: str
    file_size: int
    content_type: str

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> AttachmentUploadSpec:
        """Build a AttachmentUploadSpec from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed AttachmentUploadSpec instance.
        """
        return cls(
            id=int(data["id"]),
            filename=data["filename"],
            file_size=int(data["file_size"]),
            content_type=data["content_type"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Return this upload specification in Fluxer's request shape.

        Returns:
            The serialized representation with supported fields preserved.
        """
        return {
            "id": self.id,
            "filename": self.filename,
            "file_size": self.file_size,
            "content_type": self.content_type,
        }


@dataclass(slots=True)
class AttachmentUploadPart:
    """One presigned multipart upload part returned by Fluxer.

    Attributes:
        part_number: One-based index of this multipart upload part.
        upload_url: Signed PUT capability; upload without an account Authorization header.
    """

    part_number: int
    upload_url: str

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> AttachmentUploadPart:
        """Build a AttachmentUploadPart from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed AttachmentUploadPart instance.
        """
        return cls(part_number=int(data["part_number"]), upload_url=data["upload_url"])


@dataclass(slots=True)
class AttachmentUpload:
    """Presigned upload details for one Fluxer message attachment.

    Attributes:
        id: Identity of the object used by this operation.
        filename: Filename presented to the server and recipients.
        upload_filename: Opaque upload key claimed by the message attachment payload.
        file_size: Exact file length in bytes declared when planning the upload.
        content_type: Content type used by this operation.
        upload_mode: Server-selected singlepart or multipart transfer mode.
        upload_url: Signed PUT capability; upload without an account Authorization header.
        upload_id: Identity of the upload used by this operation.
        part_size: Planned byte count per multipart chunk, except the final remainder.
        parts: Signed part destinations in ascending part-number order.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        is_multipart: Return whether this upload requires multipart completion.
    """

    id: int
    filename: str
    upload_filename: str
    file_size: int
    content_type: str
    upload_mode: str
    upload_url: str | None = None
    upload_id: str | None = None
    part_size: int | None = None
    parts: list[AttachmentUploadPart] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> AttachmentUpload:
        """Build a AttachmentUpload from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed AttachmentUpload instance.
        """
        return cls(
            id=int(data["id"]),
            filename=data["filename"],
            upload_filename=data["upload_filename"],
            file_size=int(data["file_size"]),
            content_type=data["content_type"],
            upload_mode=data["upload_mode"],
            upload_url=data.get("upload_url"),
            upload_id=data.get("upload_id"),
            part_size=_maybe_int(data.get("part_size")),
            parts=[
                AttachmentUploadPart.from_data(part) for part in data.get("parts", [])
            ],
            raw_data=data,
        )

    @property
    def is_multipart(self) -> bool:
        """Return whether this upload requires multipart completion.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.upload_mode == "multipart"

    def to_attachment_payload(
        self, *, description: str | None = None
    ) -> dict[str, Any]:
        """Return the message `attachments` payload item for this upload.

        Args:
            description: Descriptive text associated with this object.

        Returns:
            The result of this operation.
        """
        payload: dict[str, Any] = {
            "id": self.id,
            "filename": self.filename,
            "upload_filename": self.upload_filename,
        }
        if description is not None:
            payload["description"] = description
        return payload


@dataclass(slots=True)
class AttachmentUploadPlan:
    """Response from Fluxer's presigned message attachment upload route.

    Attributes:
        attachments: Attachment metadata; an edit retains only the supplied attachment IDs.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    attachments: list[AttachmentUpload] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> AttachmentUploadPlan:
        """Build a AttachmentUploadPlan from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed AttachmentUploadPlan instance.
        """
        return cls(
            attachments=[
                AttachmentUpload.from_data(item) for item in data.get("attachments", [])
            ],
            raw_data=data,
        )


@dataclass(slots=True)
class CompletedAttachmentUpload:
    """Finalized Fluxer multipart attachment upload key.

    Attributes:
        upload_filename: Opaque upload key claimed by the message attachment payload.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    upload_filename: str
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> CompletedAttachmentUpload:
        """Build a CompletedAttachmentUpload from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed CompletedAttachmentUpload instance.
        """
        return cls(upload_filename=data["upload_filename"], raw_data=data)


@dataclass(slots=True)
class CompletedAttachmentUploadList:
    """Response from Fluxer's multipart attachment completion route.

    Attributes:
        uploads: Successfully completed multipart upload keys.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    uploads: list[CompletedAttachmentUpload] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> CompletedAttachmentUploadList:
        """Build a CompletedAttachmentUploadList from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed CompletedAttachmentUploadList instance.
        """
        return cls(
            uploads=[
                CompletedAttachmentUpload.from_data(item)
                for item in data.get("uploads", [])
            ],
            raw_data=data,
        )


@dataclass(slots=True)
class SavedMessage:
    """A private saved-message entry for the authenticated user.

    Attributes:
        id: The ID of the saved entry.
        message_id: The ID of the saved message.
        channel_id: The channel the message was saved from.
        guild_id: Guild identity retained from the payload or operation context.
        status: The saved message status of the entry.
        saved_at: Legacy timestamp retained only when explicitly supplied.
        message: The message as the caller can currently see it, or null.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: int | None = None
    message_id: int | None = None
    channel_id: int | None = None
    guild_id: int | None = None
    status: str | None = None
    saved_at: str | None = None
    message: Message | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> SavedMessage:
        """Build a SavedMessage from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed SavedMessage instance.
        """
        payload = _unwrap(data, "saved_message", "entry")
        message_data = payload.get("message")
        message = None
        if isinstance(message_data, dict):
            from .models import Message

            message = Message.from_data(message_data, http)
        return cls(
            id=_maybe_int(payload.get("id")),
            message_id=_maybe_int(
                payload.get("message_id") or (message_data or {}).get("id")
            ),
            channel_id=_maybe_int(
                payload.get("channel_id") or (message_data or {}).get("channel_id")
            ),
            guild_id=_maybe_int(
                payload.get("guild_id") or (message_data or {}).get("guild_id")
            ),
            status=payload.get("status"),
            saved_at=payload.get("saved_at"),
            message=message,
            raw_data=data,
        )


@dataclass(slots=True)
class ScheduledMessage:
    """Compatibility data for scheduled-message payloads.

    No scheduled-message workflow is implemented or documented by this package.

    Attributes:
        id: Identity of the object used by this operation.
        channel_id: Channel identity retained from the payload or operation context.
        scheduled_at: Scheduled at used by this operation.
        scheduled_local_at: Scheduled local at used by this operation.
        timezone: Timezone used by this operation.
        status: Presence status accepted by the Fluxer Gateway.
        status_reason: Status reason used by this operation.
        payload: Operation-specific fields in the documented request shape.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: str
    channel_id: int | None = None
    scheduled_at: str | None = None
    scheduled_local_at: str | None = None
    timezone: str | None = None
    status: str | None = None
    status_reason: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> ScheduledMessage:
        """Build a ScheduledMessage from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed ScheduledMessage instance.
        """
        payload = _unwrap(data, "scheduled_message")
        return cls(
            id=str(payload.get("id") or payload.get("scheduled_message_id")),
            channel_id=_maybe_int(payload.get("channel_id")),
            scheduled_at=payload.get("scheduled_at"),
            scheduled_local_at=payload.get("scheduled_local_at"),
            timezone=payload.get("timezone"),
            status=payload.get("status"),
            status_reason=payload.get("status_reason"),
            payload=payload.get("message") or payload.get("payload") or {},
            raw_data=data,
        )


@dataclass(slots=True)
class Mention:
    """A recent mention entry for the authenticated user.

    Attributes:
        message: Message supplying content and channel/guild context.
        message_id: Message identity supplied by the event or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        guild_id: Guild identity retained from the payload or operation context.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    message: Message | None = None
    message_id: int | None = None
    channel_id: int | None = None
    guild_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Mention:
        """Build a Mention from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Mention instance.
        """
        payload = _unwrap(data, "mention", "message")
        message = None
        if "content" in payload and "author" in payload:
            from .models import Message

            message = Message.from_data(payload, http)
        return cls(
            message=message,
            message_id=_maybe_int(payload.get("id") or payload.get("message_id")),
            channel_id=_maybe_int(payload.get("channel_id")),
            guild_id=_maybe_int(payload.get("guild_id")),
            raw_data=data,
        )


@dataclass(slots=True)
class Relationship:
    """A Fluxer account relationship. User-token sensitive.

    Attributes:
        id: The ID of the related account.
        user_id: Identity of the user used by this operation.
        type: The relationship type.
        nickname: The caller-private nickname for the related account, or null when none is set.
        since: The time at which the record's current type was established.
        user: The related account.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        share_voice_activity: Whether the caller shares voice activity with the related account.
        friend_shares_voice_activity: Whether the related account shares voice activity with the caller.
    """

    id: int | None = None
    user_id: int | None = None
    type: str | int | None = None
    nickname: str | None = None
    since: str | None = None
    user: User | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    share_voice_activity: bool | None = None
    friend_shares_voice_activity: bool | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> Relationship:
        """Build a Relationship from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Relationship instance.
        """
        payload = _unwrap(data, "relationship")
        user_data = payload.get("user")
        user = None
        if isinstance(user_data, dict):
            from .models import User

            user = User.from_data(user_data, http)
        return cls(
            id=_maybe_int(payload.get("id")),
            user_id=_maybe_int(payload.get("user_id") or (user_data or {}).get("id")),
            type=payload.get("type"),
            nickname=payload.get("nickname"),
            since=payload.get("since") or payload.get("created_at"),
            user=user,
            share_voice_activity=payload.get("share_voice_activity"),
            friend_shares_voice_activity=payload.get("friend_shares_voice_activity"),
            raw_data=data,
        )


@dataclass(slots=True)
class FavoriteMeme:
    """A Fluxer saved-media favorite meme entry. User-token sensitive.

    Attributes:
        id: The ID of the meme.
        owner_id: Identity of the owning account when supplied by the object.
        name: The display name of the meme (1-100 characters).
        tags: The search tags stored on the meme, each 1-30 characters.
        url: The Fluxer attachment URL of the stored copy.
        filename: The filename of the stored copy.
        content_type: The MIME type of the stored copy.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        user_id: The ID of the owning account.
        alt_text: The accessibility description of the media, or null when none is set.
        attachment_id: The ID of the attachment holding the durable Fluxer copy.
        content_hash: The content hash used for deduplication, or null when it is unavailable.
        size: The stored size of the copy in bytes.
        width: The width of the media in pixels, or null when not applicable or unknown.
        height: The height of the media in pixels, or null when not applicable or unknown.
        duration: The duration of the media in seconds, or null when not applicable or unknown.
        is_gifv: Whether the stored media is animated or a video converted from a GIF.
        gif_slug: The provider-issued slug this meme was sourced from, or null.
        gif_provider: The name of the GIF provider that issued `gif_slug`, or null.
        media: The provider format map for a GIF-sourced meme, or null.
        placeholder: The compact thumbhash placeholder recorded at save time, or null.
    """

    id: str
    owner_id: int | None = None
    name: str | None = None
    tags: list[str] = field(default_factory=list)
    url: str | None = None
    filename: str | None = None
    content_type: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    user_id: int | None = None
    alt_text: str | None = None
    attachment_id: int | None = None
    content_hash: str | None = None
    size: int | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    is_gifv: bool | None = None
    gif_slug: str | None = None
    gif_provider: str | None = None
    media: dict[str, Any] | None = None
    placeholder: str | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> FavoriteMeme:
        """Build a FavoriteMeme from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed FavoriteMeme instance.
        """
        payload = _unwrap(data, "meme", "favorite_meme")
        return cls(
            id=str(payload.get("id") or payload.get("meme_id")),
            owner_id=_maybe_int(payload.get("owner_id") or payload.get("user_id")),
            name=payload.get("name"),
            tags=list(payload.get("tags") or []),
            url=payload.get("url"),
            filename=payload.get("filename"),
            content_type=payload.get("content_type"),
            user_id=int(payload["user_id"])
            if payload.get("user_id") is not None
            else None,
            alt_text=payload.get("alt_text"),
            attachment_id=int(payload["attachment_id"])
            if payload.get("attachment_id") is not None
            else None,
            content_hash=payload.get("content_hash"),
            size=payload.get("size"),
            width=payload.get("width"),
            height=payload.get("height"),
            duration=payload.get("duration"),
            is_gifv=payload.get("is_gifv"),
            gif_slug=payload.get("gif_slug"),
            gif_provider=payload.get("gif_provider"),
            media=payload.get("media"),
            placeholder=payload.get("placeholder"),
            raw_data=data,
        )


@dataclass(slots=True)
class SearchResult:
    """A Fluxer message search result page.

    Attributes:
        messages: Message hits in server result order.
        channels: Channel objects providing context for the returned hits.
        total: Total used by this operation.
        hits_per_page: Maximum search hits requested in one result page.
        page: Page number passed to the search operation.
        cursor: Opaque response metadata; the API uses page for pagination.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        next_cursor: Compatibility alias for cursor.
    """

    messages: list[Message] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    total: int = 0
    hits_per_page: int = 25
    page: int = 1
    cursor: list[str] | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def next_cursor(self) -> list[str] | None:
        """Compatibility alias for cursor.

        Fluxer does not accept this cursor for pagination; use `page` instead.

        Returns:
            The result of this operation.
        """
        return self.cursor

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> SearchResult:
        """Build a SearchResult from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed SearchResult instance.
        """
        from .models import Channel, Message

        raw_messages = data.get("messages", data.get("results", []))
        raw_channels = data.get("channels") or []
        channels = [
            Channel.from_data(item, http)
            for item in raw_channels
            if isinstance(item, dict)
        ]
        channels_by_id = {channel.id: channel for channel in channels}
        messages = [
            Message.from_data(item.get("message", item), http)
            for item in raw_messages
            if isinstance(item, dict)
        ]
        for message in messages:
            message._channel = channels_by_id.get(message.channel_id)

        total = data.get("total")
        if total is None:
            total = data.get("total_results", 0)
        cursor = data.get("cursor")
        return cls(
            messages=messages,
            channels=channels,
            total=_maybe_int(total) or 0,
            hits_per_page=_maybe_int(data.get("hits_per_page")) or 25,
            page=_maybe_int(data.get("page")) or 1,
            cursor=[str(item) for item in cursor] if isinstance(cursor, list) else None,
            raw_data=data,
        )


@dataclass(slots=True)
class SearchIndexing:
    """Indicates that Fluxer is preparing one or more message search indexes.

    Attributes:
        indexing: Indexing used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    indexing: Literal[True] = True
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> SearchIndexing:
        """Build a SearchIndexing from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed SearchIndexing instance.
        """
        return cls(raw_data=data)


SearchResponse: TypeAlias = SearchResult | SearchIndexing


def parse_search_response(
    data: dict[str, Any], http: HTTPClient | None = None
) -> SearchResponse:
    """Parse either successful body returned by message search.

    Args:
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
        http: Transport to bind for subsequent operations; None creates an unbound model.

    Returns:
        The result of this operation.
    """
    if data.get("indexing") is True:
        return SearchIndexing.from_data(data)
    return SearchResult.from_data(data, http)


@dataclass(slots=True)
class ReadState:
    """A Fluxer read-state entry for a channel.

    Attributes:
        channel_id: Channel identity retained from the payload or operation context.
        mention_count: The number of mentions stored for the channel (0-2,147,483,647).
        last_message_id: The highest message ID the account has read through, or null when the entry stores no watermark.
        last_pin_timestamp: The time of the last acknowledged pin, or null when pins have never been acknowledged.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        id: The ID of the channel the read state belongs to.
        version: The read state version as a canonical decimal unsigned 64-bit string.
    """

    channel_id: int | None = None
    mention_count: int | None = None
    last_message_id: int | None = None
    last_pin_timestamp: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    id: int | None = None
    version: str | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> ReadState:
        """Build a ReadState from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed ReadState instance.
        """
        payload = _unwrap(data, "read_state")
        return cls(
            channel_id=_maybe_int(payload.get("id") or payload.get("channel_id")),
            mention_count=_maybe_int(payload.get("mention_count")),
            last_message_id=_maybe_int(payload.get("last_message_id")),
            last_pin_timestamp=payload.get("last_pin_timestamp"),
            id=_maybe_int(payload.get("id")),
            version=payload.get("version"),
            raw_data=data,
        )


@dataclass(slots=True)
class FavoriteGif:
    """A resolved Fluxer favorite GIF/media proxy entry.

    Attributes:
        url: Source URL of the GIF.
        proxy_url: Media Proxy URL for the preview format.
        media: Formats keyed by GIF media format name.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        width: Width of the preview format in pixels.
        height: Height of the preview format in pixels.
        content_type: Media type of the media addressed by `proxy_url`.
        placeholder: Compact thumbhash placeholder.
    """

    url: str | None = None
    proxy_url: str | None = None
    media: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    width: int | None = None
    height: int | None = None
    content_type: str | None = None
    placeholder: str | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> FavoriteGif:
        """Build a FavoriteGif from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed FavoriteGif instance.
        """
        payload = _unwrap(data, "gif", "entry")
        return cls(
            url=payload.get("url") or payload.get("source_url"),
            proxy_url=payload.get("proxy_url") or payload.get("media_proxy_url"),
            media=payload.get("media") or {},
            width=payload.get("width"),
            height=payload.get("height"),
            content_type=payload.get("content_type"),
            placeholder=payload.get("placeholder"),
            raw_data=data,
        )


@dataclass(slots=True)
class GiftCode:
    """A Fluxer premium gift code or gift-code metadata entry.

    User-token sensitive when retrieved from the current user's gift inventory.

    Attributes:
        code: The code presented to Redeem gift.
        duration_type: The gift duration unit that `duration_quantity` is measured in.
        duration_quantity: The number of `duration_type` units the gift grants.
        redeemed: Whether the code has already been redeemed.
        created_at: Created at used by this operation.
        redeemed_at: Redeemed at used by this operation.
        created_by: The account that created the gift.
        redeemed_by: Redeemed by used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    code: str
    duration_type: str | None = None
    duration_quantity: int | None = None
    redeemed: bool | None = None
    created_at: str | None = None
    redeemed_at: str | None = None
    created_by: User | None = None
    redeemed_by: User | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> GiftCode:
        """Build a GiftCode from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed GiftCode instance.
        """
        payload = _unwrap(data, "gift", "gift_code")
        from .models import User

        created_by_data = payload.get("created_by")
        redeemed_by_data = payload.get("redeemed_by")
        return cls(
            code=payload["code"],
            duration_type=payload.get("duration_type"),
            duration_quantity=_maybe_int(payload.get("duration_quantity")),
            redeemed=payload.get("redeemed")
            if payload.get("redeemed") is not None
            else payload.get("redeemed_at") is not None,
            created_at=payload.get("created_at"),
            redeemed_at=payload.get("redeemed_at"),
            created_by=User.from_data(created_by_data, http)
            if isinstance(created_by_data, dict)
            else None,
            redeemed_by=User.from_data(redeemed_by_data, http)
            if isinstance(redeemed_by_data, dict)
            else None,
            raw_data=data,
        )


@dataclass(slots=True)
class PackSummary:
    """Compatibility container for pack-like metadata.

    The checked-in platform contract provides no corresponding pack workflow.

    Attributes:
        id: Identity of the object used by this operation.
        name: Name to assign or resolve in this operation.
        description: Descriptive text associated with this object.
        type: Type used by this operation.
        creator_id: Identity of the creator used by this operation.
        created_at: Created at used by this operation.
        updated_at: Updated at used by this operation.
        installed_at: Installed at used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: int
    name: str
    description: str | None = None
    type: str | None = None
    creator_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    installed_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> PackSummary:
        """Build a PackSummary from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed PackSummary instance.
        """
        payload = _unwrap(data, "pack")
        return cls(
            id=int(payload["id"]),
            name=payload.get("name", ""),
            description=payload.get("description"),
            type=payload.get("type"),
            creator_id=_maybe_int(payload.get("creator_id")),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
            installed_at=payload.get("installed_at"),
            raw_data=data,
        )


@dataclass(slots=True)
class PackDashboardSection:
    """Compatibility container for one section of pack-like metadata.

    The package implements no pack dashboard workflow.

    Attributes:
        installed_limit: Installed limit used by this operation.
        created_limit: Created limit used by this operation.
        installed: Installed used by this operation.
        created: Created used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    installed_limit: int | None = None
    created_limit: int | None = None
    installed: list[PackSummary] = field(default_factory=list)
    created: list[PackSummary] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> PackDashboardSection:
        """Build a PackDashboardSection from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed PackDashboardSection instance.
        """
        payload = _unwrap(data, "section")
        return cls(
            installed_limit=_maybe_int(payload.get("installed_limit")),
            created_limit=_maybe_int(payload.get("created_limit")),
            installed=[
                PackSummary.from_data(item, http)
                for item in payload.get("installed", [])
                if isinstance(item, dict)
            ],
            created=[
                PackSummary.from_data(item, http)
                for item in payload.get("created", [])
                if isinstance(item, dict)
            ],
            raw_data=data,
        )


@dataclass(slots=True)
class PackDashboard:
    """Compatibility container for pack-like dashboard metadata.

    The package implements no pack dashboard workflow.

    Attributes:
        emoji: Emoji used by this operation.
        sticker: Sticker used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    emoji: PackDashboardSection
    sticker: PackDashboardSection
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> PackDashboard:
        """Build a PackDashboard from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed PackDashboard instance.
        """
        payload = _unwrap(data, "dashboard", "packs")
        return cls(
            emoji=PackDashboardSection.from_data(payload.get("emoji", {}), http),
            sticker=PackDashboardSection.from_data(payload.get("sticker", {}), http),
            raw_data=data,
        )


@dataclass(slots=True)
class EntranceSound:
    """A Fluxer entrance sound library entry. User-token sensitive.

    Attributes:
        id: The ID of the sound.
        name: The display label shown for the clip (1-32 characters).
        hash: The content digest of the stored audio, 16 hexadecimal characters.
        extension: The stored extension, one of `mp3`, `ogg`, `m4a`, and `wav`, chosen by the detected container.
        content_type: The MIME type the clip is stored and served with, derived from `extension`.
        duration_ms: The measured duration in milliseconds (0-5200).
        size_bytes: The decoded size in bytes (0-1048576).
        url: The absolute CDN URL the clip is fetched from.
        created_at: The time the clip was uploaded.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: int
    name: str
    hash: str | None = None
    extension: str | None = None
    content_type: str | None = None
    duration_ms: int | None = None
    size_bytes: int | None = None
    url: str | None = None
    created_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> EntranceSound:
        """Build a EntranceSound from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed EntranceSound instance.
        """
        payload = _unwrap(data, "sound", "entrance_sound")
        return cls(
            id=int(payload["id"]),
            name=payload.get("name", ""),
            hash=payload.get("hash"),
            extension=payload.get("extension"),
            content_type=payload.get("content_type"),
            duration_ms=_maybe_int(payload.get("duration_ms")),
            size_bytes=_maybe_int(payload.get("size_bytes")),
            url=payload.get("url"),
            created_at=payload.get("created_at"),
            raw_data=data,
        )


@dataclass(slots=True)
class EntranceSoundSelection:
    """A selected entrance sound for one Fluxer scope.

    Attributes:
        scope_id: Entrance sound scope the selection applies to.
        sound_id: The clip assigned to that scope.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    scope_id: str
    sound_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> EntranceSoundSelection:
        """Build a EntranceSoundSelection from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed EntranceSoundSelection instance.
        """
        payload = _unwrap(data, "selection")
        return cls(
            scope_id=payload.get("scope_id", ""),
            sound_id=_maybe_int(payload.get("sound_id")),
            raw_data=data,
        )


@dataclass(slots=True)
class EntranceSoundLibrary:
    """Fluxer's current-user entrance sound library and active selections.

    Attributes:
        sounds: Owned entrance sound clips available for selection.
        selections: Scope-to-sound assignments; unset scopes are absent.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    sounds: list[EntranceSound] = field(default_factory=list)
    selections: list[EntranceSoundSelection] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> EntranceSoundLibrary:
        """Build a EntranceSoundLibrary from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed EntranceSoundLibrary instance.
        """
        payload = _unwrap(data, "library", "entrance_sounds")
        return cls(
            sounds=[
                EntranceSound.from_data(item, http)
                for item in payload.get("sounds", [])
                if isinstance(item, dict)
            ],
            selections=[
                EntranceSoundSelection.from_data(item, http)
                for item in payload.get("selections", [])
                if isinstance(item, dict)
            ],
            raw_data=data,
        )


@dataclass(slots=True)
class Theme:
    """A Fluxer custom theme create response. User-token sensitive.

    Attributes:
        id: Identity of the object used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: str
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Theme:
        """Build a Theme from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Theme instance.
        """
        payload = _unwrap(data, "theme")
        return cls(id=str(payload["id"]), raw_data=data)


@dataclass(slots=True)
class BanEntry:
    """A Fluxer guild ban entry.

    Attributes:
        user: The banned account.
        reason: The stored ban reason, or null when none was recorded.
        moderator_id: The account that issued or most recently replaced the ban.
        banned_at: Time the ban was issued or most recently replaced.
        expires_at: Time a temporary ban stops applying, or null for a permanent ban.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    user: User
    reason: str | None = None
    moderator_id: int | None = None
    banned_at: str | None = None
    expires_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> BanEntry:
        """Build a BanEntry from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed BanEntry instance.
        """
        payload = _unwrap(data, "ban")
        from .models import User

        return cls(
            user=User.from_data(payload["user"], http),
            reason=payload.get("reason"),
            moderator_id=_maybe_int(payload.get("moderator_id")),
            banned_at=payload.get("banned_at"),
            expires_at=payload.get("expires_at"),
            raw_data=data,
        )


@dataclass(slots=True)
class DiscoveryGuild:
    """A guild entry returned by Fluxer's discovery directory.

    Attributes:
        id: The ID of the guild.
        name: The name of the guild at index time.
        description: The description supplied on the application, or null.
        member_count: The current member count of the guild.
        online_count: The current online member count of the guild.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        icon: The icon hash of the guild, or null when it stores none.
        banner: The banner hash of the guild, or null when it stores none.
        category_type: The discovery category the listing is filed under.
        primary_language: The supported primary language code of the listing, or null.
        custom_tags: The normalised custom tags of the listing.
        features: The guild features the guild has.
        verification_level: The effective verification level of the guild.
    """

    id: int | None = None
    name: str | None = None
    description: str | None = None
    member_count: int | None = None
    online_count: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    icon: str | None = None
    banner: str | None = None
    category_type: int | None = None
    primary_language: str | None = None
    custom_tags: list[str] | None = None
    features: list[str] | None = None
    verification_level: int | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> DiscoveryGuild:
        """Build a DiscoveryGuild from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed DiscoveryGuild instance.
        """
        payload = _unwrap(data, "guild", "discovery_guild")
        return cls(
            id=_maybe_int(payload.get("id") or payload.get("guild_id")),
            name=payload.get("name"),
            description=payload.get("description"),
            member_count=_maybe_int(payload.get("member_count")),
            online_count=_maybe_int(payload.get("online_count")),
            icon=payload.get("icon"),
            banner=payload.get("banner"),
            category_type=payload.get("category_type"),
            primary_language=payload.get("primary_language"),
            custom_tags=payload.get("custom_tags"),
            features=payload.get("features"),
            verification_level=payload.get("verification_level"),
            raw_data=data,
        )


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
        payload = _unwrap(data, "vanity_url", "vanity")
        return cls(
            code=payload.get("code") or payload.get("vanity_url_code"),
            uses=_maybe_int(payload.get("uses")),
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
        payload = _unwrap(data, "application", "discovery_application")
        return cls(
            guild_id=_maybe_int(payload.get("guild_id")),
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
        payload = _unwrap(data, "discovery", "status")
        app_data = payload.get("application") or payload.get("discovery_application")
        return cls(
            guild_id=_maybe_int(payload.get("guild_id")),
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
        payload = _unwrap(data, "guild")
        return cls(
            guild_id=_maybe_int(payload.get("id") or payload.get("guild_id")),
            owner_id=_maybe_int(payload.get("owner_id")),
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


@dataclass(slots=True)
class Team:
    """Compatibility container for team-like metadata.

    No team resource workflow is implemented or claimed by this package.

    Attributes:
        id: Identity of the object used by this operation.
        name: Name to assign or resolve in this operation.
        owner_user_id: Identity of the owner user used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: int | None = None
    name: str | None = None
    owner_user_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Team:
        """Build a Team from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Team instance.
        """
        return cls(
            id=_maybe_int(data.get("id")),
            name=data.get("name"),
            owner_user_id=_maybe_int(data.get("owner_user_id") or data.get("owner_id")),
            raw_data=data,
        )


@dataclass(slots=True)
class AppInfo:
    """A Fluxer OAuth2 application.

    This represents Fluxer application metadata where the
    OpenAPI exposes matching OAuth application fields.

    Attributes:
        id: Identity of the object used by this operation.
        name: Name to assign or resolve in this operation.
        redirect_uris: Redirect uris used by this operation.
        bot_public: Bot public used by this operation.
        bot_require_code_grant: Whether adding this application requires an authorization-code grant.
        client_secret: Client secret used by this operation.
        bot: Client owning this command, cog, or context.
        team: Team used by this operation.
        description: Descriptive text associated with this object.
        icon: Replacement guild icon; omission preserves it and None clears it.
        verify_key: Verify key used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        owner: Return the application owner when the response supplies that user.
    """

    id: int
    name: str
    redirect_uris: list[str] = field(default_factory=list)
    bot_public: bool = False
    bot_require_code_grant: bool = False
    client_secret: str | None = field(default=None, repr=False)
    bot: User | None = None
    _owner: User | None = field(default=None, repr=False)
    team: Team | None = None
    description: str | None = None
    icon: str | None = None
    verify_key: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> AppInfo:
        """Build a AppInfo from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed AppInfo instance.
        """
        payload = _unwrap(data, "application", "app")
        from .models import User

        bot_data = payload.get("bot")
        bot = None
        if isinstance(bot_data, dict):
            from .models import User

            bot = User.from_data(bot_data, http)
        team_data = payload.get("team")
        return cls(
            id=int(payload["id"]),
            name=payload.get("name", ""),
            redirect_uris=list(payload.get("redirect_uris") or []),
            bot_public=bool(payload.get("bot_public", False)),
            bot_require_code_grant=bool(payload.get("bot_require_code_grant", False)),
            client_secret=payload.get("client_secret"),
            bot=bot,
            _owner=User.from_data(payload["owner"], http)
            if payload.get("owner") is not None
            else None,
            team=Team.from_data(team_data, http)
            if isinstance(team_data, dict)
            else None,
            description=payload.get("description"),
            icon=payload.get("icon"),
            verify_key=payload.get("verify_key"),
            raw_data=data,
        )

    @property
    def owner(self) -> User | None:
        """Return the application owner when the response supplies that user.

        Returns:
            The result of this operation.
        """
        return self._owner


@dataclass(slots=True)
class AuthSession:
    """A Fluxer auth session. User-token sensitive.

    Attributes:
        id: Identity of the object used by this operation.
        id_hash: The base64url SHA-256 digest of the session token.
        masked_ip: The semi-redacted IP address recorded for the session.
        client_info: The parsed client metadata recorded when the session was created.
        approx_last_used_at: The approximate time of the last request that used this session.
        current: Whether this session supplied the credential for the current request.
        ip: Ip used by this operation.
        user_agent: User agent used by this operation.
        created_at: Created at used by this operation.
        last_used_at: Last used at used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: str | None = None
    id_hash: str | None = None
    masked_ip: str | None = None
    client_info: dict[str, Any] | None = None
    approx_last_used_at: str | None = None
    current: bool | None = None
    ip: str | None = None
    user_agent: str | None = None
    created_at: str | None = None
    last_used_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> AuthSession:
        """Build a AuthSession from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed AuthSession instance.
        """
        payload = _unwrap(data, "session", "auth_session")
        return cls(
            id=payload.get("id_hash"),
            id_hash=payload.get("id_hash"),
            masked_ip=payload.get("masked_ip"),
            client_info=payload.get("client_info"),
            approx_last_used_at=payload.get("approx_last_used_at"),
            current=payload.get("current"),
            ip=payload.get("masked_ip"),
            user_agent=payload.get("user_agent"),
            created_at=payload.get("created_at"),
            last_used_at=payload.get("approx_last_used_at"),
            raw_data=data,
        )


@dataclass(slots=True)
class MFAState:
    """Authenticator availability from a sudo-mode-required error response.

    The top-level has_mfa flag is independent from the nested methods mapping.
    Direct method-availability mappings are also accepted; has_mfa remains None
    when the payload does not supply it.

    Attributes:
        totp: Whether TOTP proof is available.
        webauthn: Whether WebAuthn proof is available.
        has_mfa: Whether the account has an enrolled authenticator.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    totp: bool | None = None
    webauthn: bool | None = None
    has_mfa: bool | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> MFAState:
        """Build a MFAState from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed MFAState instance.
        """
        payload = _unwrap(data, "mfa", "state")
        methods = payload.get("methods", payload)
        return cls(
            totp=methods.get("totp"),
            webauthn=methods.get("webauthn"),
            has_mfa=payload.get("has_mfa"),
            raw_data=data,
        )


@dataclass(slots=True)
class WebAuthnCredential:
    """A Fluxer WebAuthn credential summary. User-token sensitive.

    Attributes:
        id: Base64url credential ID.
        name: User-assigned credential name (1-100 characters).
        created_at: The time Register WebAuthn credential stored the credential.
        last_used_at: Most recent successful authentication.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: str | None = None
    name: str | None = None
    created_at: str | None = None
    last_used_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> WebAuthnCredential:
        """Build a WebAuthnCredential from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed WebAuthnCredential instance.
        """
        payload = _unwrap(data, "credential", "webauthn_credential")
        return cls(
            id=str(payload.get("id") or payload.get("credential_id") or ""),
            name=payload.get("name"),
            created_at=payload.get("created_at"),
            last_used_at=payload.get("last_used_at"),
            raw_data=data,
        )


@dataclass(slots=True)
class UserSettings:
    """Fluxer current-user settings. User-token sensitive.

    Attributes:
        theme: Theme used by this operation.
        status: Presence status accepted by the Fluxer Gateway.
        locale: Locale used by this operation.
        status_resets_at: The time at which the scheduled status reset applies, or null.
        status_resets_to: Presence status applied by the scheduled reset, or null.
        restricted_guilds: The guilds where member direct messages are restricted.
        bot_restricted_guilds: The guilds where bot direct messages are restricted.
        default_guilds_restricted: Whether newly joined guilds restrict member direct messages.
        bot_default_guilds_restricted: Whether newly joined guilds restrict bot direct messages.
        inline_attachment_media: Whether attachment media is rendered inline.
        inline_embed_media: Whether embed media is rendered inline.
        gif_auto_play: Whether GIF media plays automatically.
        render_embeds: Whether message embeds are rendered.
        render_reactions: Whether message reactions are rendered.
        animate_emoji: Whether custom emoji animate.
        animate_stickers: Sticker animation setting.
        render_spoilers: Spoiler rendering setting.
        message_display_compact: Whether messages use compact display.
        friend_source_flags: Friend source flags.
        incoming_call_flags: Incoming call flags.
        group_dm_add_permission_flags: Group DM add permission flags.
        guild_folders: The user-owned guild sidebar layout.
        custom_status: The current custom status, or null when none is set.
        afk_timeout: The idle time in seconds before the account is presented as away.
        time_format: Time format setting.
        developer_mode: Whether developer mode is enabled.
        trusted_domains: The external link domains the account trusts.
        default_hide_muted_channels: Whether newly joined guilds hide muted channels.
        sensitive_content_friend_dm_filter: Sensitive media filter for friend direct messages.
        sensitive_content_non_friend_dm_filter: Sensitive media filter for non-friend direct messages.
        sensitive_content_guild_filter: Guild sensitive media filter.
        suppress_unprivileged_self_mentions: Whether direct and reply mentions from unprivileged users are suppressed.
        suppress_unprivileged_self_mentions_bypass_user_ids: The users exempt from mention suppression.
        staff_dm_access_user_ids: The users granted staff direct message access.
        synced_preferences: The base64-encoded synced preferences message.
        profile_privacy: Profile privacy level.
        default_share_voice_activity: Whether a newly accepted friend relationship starts with voice activity sharing on.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    theme: str | None = None
    status: str | None = None
    locale: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    status_resets_at: str | None = None
    status_resets_to: str | None = None
    restricted_guilds: list[int] = field(default_factory=list)
    bot_restricted_guilds: list[int] = field(default_factory=list)
    default_guilds_restricted: bool | None = None
    bot_default_guilds_restricted: bool | None = None
    inline_attachment_media: bool | None = None
    inline_embed_media: bool | None = None
    gif_auto_play: bool | None = None
    render_embeds: bool | None = None
    render_reactions: bool | None = None
    animate_emoji: bool | None = None
    animate_stickers: int | None = None
    render_spoilers: int | None = None
    message_display_compact: bool | None = None
    friend_source_flags: int | None = None
    incoming_call_flags: int | None = None
    group_dm_add_permission_flags: int | None = None
    guild_folders: list[dict[str, Any]] = field(default_factory=list)
    custom_status: dict[str, Any] | None = None
    afk_timeout: int | None = None
    time_format: int | None = None
    developer_mode: bool | None = None
    trusted_domains: list[str] = field(default_factory=list)
    default_hide_muted_channels: bool | None = None
    sensitive_content_friend_dm_filter: int | None = None
    sensitive_content_non_friend_dm_filter: int | None = None
    sensitive_content_guild_filter: int | None = None
    suppress_unprivileged_self_mentions: bool | None = None
    suppress_unprivileged_self_mentions_bypass_user_ids: list[int] = field(
        default_factory=list
    )
    staff_dm_access_user_ids: list[int] = field(default_factory=list)
    synced_preferences: str | None = None
    profile_privacy: int | None = None
    default_share_voice_activity: bool | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> UserSettings:
        """Build a UserSettings from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed UserSettings instance.
        """
        payload = _unwrap(data, "settings", "user_settings")
        return cls(
            theme=payload.get("theme"),
            status=payload.get("status"),
            locale=payload.get("locale"),
            status_resets_at=payload.get("status_resets_at"),
            status_resets_to=payload.get("status_resets_to"),
            restricted_guilds=[
                int(item) for item in payload.get("restricted_guilds", [])
            ],
            bot_restricted_guilds=[
                int(item) for item in payload.get("bot_restricted_guilds", [])
            ],
            default_guilds_restricted=payload.get("default_guilds_restricted"),
            bot_default_guilds_restricted=payload.get("bot_default_guilds_restricted"),
            inline_attachment_media=payload.get("inline_attachment_media"),
            inline_embed_media=payload.get("inline_embed_media"),
            gif_auto_play=payload.get("gif_auto_play"),
            render_embeds=payload.get("render_embeds"),
            render_reactions=payload.get("render_reactions"),
            animate_emoji=payload.get("animate_emoji"),
            animate_stickers=payload.get("animate_stickers"),
            render_spoilers=payload.get("render_spoilers"),
            message_display_compact=payload.get("message_display_compact"),
            friend_source_flags=payload.get("friend_source_flags"),
            incoming_call_flags=payload.get("incoming_call_flags"),
            group_dm_add_permission_flags=payload.get("group_dm_add_permission_flags"),
            guild_folders=list(payload.get("guild_folders", [])),
            custom_status=payload.get("custom_status"),
            afk_timeout=payload.get("afk_timeout"),
            time_format=payload.get("time_format"),
            developer_mode=payload.get("developer_mode"),
            trusted_domains=list(payload.get("trusted_domains", [])),
            default_hide_muted_channels=payload.get("default_hide_muted_channels"),
            sensitive_content_friend_dm_filter=payload.get(
                "sensitive_content_friend_dm_filter"
            ),
            sensitive_content_non_friend_dm_filter=payload.get(
                "sensitive_content_non_friend_dm_filter"
            ),
            sensitive_content_guild_filter=payload.get(
                "sensitive_content_guild_filter"
            ),
            suppress_unprivileged_self_mentions=payload.get(
                "suppress_unprivileged_self_mentions"
            ),
            suppress_unprivileged_self_mentions_bypass_user_ids=[
                int(item)
                for item in payload.get(
                    "suppress_unprivileged_self_mentions_bypass_user_ids", []
                )
            ],
            staff_dm_access_user_ids=[
                int(item) for item in payload.get("staff_dm_access_user_ids", [])
            ],
            synced_preferences=payload.get("synced_preferences"),
            profile_privacy=payload.get("profile_privacy"),
            default_share_voice_activity=payload.get("default_share_voice_activity"),
            raw_data=data,
        )


@dataclass(slots=True)
class UserConnection:
    """A Fluxer linked user connection. User-token sensitive.

    Attributes:
        id: The ID of the connection, unique within its connection type.
        type: Connection type.
        name: The domain or Bluesky handle shown for the connection.
        verified: Whether the most recent proof succeeded.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        visibility_flags: Connection visibility flags.
        sort_order: The display order within the account's connection list (0-2147483647).
    """

    id: str | None = None
    type: str | None = None
    name: str | None = None
    verified: bool | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    visibility_flags: int | None = None
    sort_order: int | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> UserConnection:
        """Build a UserConnection from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed UserConnection instance.
        """
        payload = _unwrap(data, "connection")
        return cls(
            id=str(payload.get("id") or ""),
            type=payload.get("type"),
            name=payload.get("name"),
            verified=payload.get("verified"),
            visibility_flags=payload.get("visibility_flags"),
            sort_order=payload.get("sort_order"),
            raw_data=data,
        )


@dataclass(slots=True)
class AuthorizedIP:
    """Compatibility view of caller-supplied IP authorization metadata.

    The current platform documentation defines no complete response matching
    these convenience fields. Missing values stay None and raw_data preserves
    the original payload; this class does not imply an implemented HTTP workflow.

    Attributes:
        ip: Ip used by this operation.
        location: Location used by this operation.
        authorized_at: Authorized at used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    ip: str | None = None
    location: str | None = None
    authorized_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> AuthorizedIP:
        """Build a AuthorizedIP from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed AuthorizedIP instance.
        """
        payload = _unwrap(data, "ip", "authorized_ip")
        return cls(
            ip=payload.get("ip") or payload.get("ip_address"),
            location=payload.get("location"),
            authorized_at=payload.get("authorized_at") or payload.get("created_at"),
            raw_data=data,
        )


@dataclass(slots=True)
class DataHarvest:
    """A Fluxer data export/harvest response. User-token sensitive.

    Attributes:
        id: Identity of the object used by this operation.
        status: The derived harvest status.
        download_url: The temporary archive download URL (1-2048 characters).
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        harvest_id: The ID of the harvest.
        created_at: When the harvest was requested.
        started_at: When the current processing attempt began, or null while the harvest is pending.
        completed_at: When the archive was written, or null when it has not been.
        failed_at: When the latest attempt recorded a failure, or null when it has not.
        file_size: The archive size in bytes as a decimal string, or null before the archive was written.
        progress_percent: Progress from 0 through 100.
        progress_step: The harvest progress step for the current stage.
        error_message: The latest attempt's failure description, or null when it has not failed.
        download_url_expires_at: When the archive's download deadline elapses, or null before completion.
        expires_at: Seven days after this response was produced.
    """

    id: str | None = None
    status: str | None = None
    download_url: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    harvest_id: int | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    failed_at: str | None = None
    file_size: str | None = None
    progress_percent: float | None = None
    progress_step: str | None = None
    error_message: str | None = None
    download_url_expires_at: str | None = None
    expires_at: str | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> DataHarvest:
        """Build a DataHarvest from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed DataHarvest instance.
        """
        payload = _unwrap(data, "harvest", "data_harvest", "export")
        return cls(
            id=str(payload["harvest_id"])
            if payload.get("harvest_id") is not None
            else None,
            status=payload.get("status"),
            download_url=payload.get("download_url") or payload.get("url"),
            harvest_id=_maybe_int(payload.get("harvest_id")),
            created_at=payload.get("created_at"),
            started_at=payload.get("started_at"),
            completed_at=payload.get("completed_at"),
            failed_at=payload.get("failed_at"),
            file_size=payload.get("file_size"),
            progress_percent=payload.get("progress_percent"),
            progress_step=payload.get("progress_step"),
            error_message=payload.get("error_message"),
            download_url_expires_at=payload.get("download_url_expires_at"),
            expires_at=payload.get("expires_at"),
            raw_data=data,
        )


@dataclass(slots=True)
class CallEligibility:
    """A Fluxer call eligibility response.

    Attributes:
        channel_id: Channel identity retained from the payload or operation context.
        can_call: Can call used by this operation.
        ringable: Whether the authenticated user can initiate an audible ring in this channel.
        active: Active used by this operation.
        silent: Whether a newly started call notifies the other recipient without audible ringing.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    channel_id: int | None = None
    can_call: bool | None = None
    ringable: bool | None = None
    active: bool | None = None
    silent: bool | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> CallEligibility:
        """Build a CallEligibility from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed CallEligibility instance.
        """
        payload = _unwrap(data, "eligibility", "call")
        return cls(
            channel_id=_maybe_int(payload.get("channel_id")),
            can_call=payload.get("can_call")
            if "can_call" in payload
            else payload.get("eligible"),
            ringable=payload.get("ringable"),
            active=payload.get("active", payload.get("has_active_call")),
            silent=payload.get("silent", payload.get("silent_mode")),
            raw_data=data,
        )


@dataclass(slots=True)
class RTCRegion:
    """A Fluxer RTC region entry.

    Attributes:
        id: The ID of the RTC region.
        name: The name shown for the region in a client.
        optimal: Optimal used by this operation.
        deprecated: Deprecated used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        emoji: The emoji the operator configured for the region.
    """

    id: str | None = None
    name: str | None = None
    optimal: bool | None = None
    deprecated: bool | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    emoji: str | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> RTCRegion:
        """Build a RTCRegion from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed RTCRegion instance.
        """
        payload = _unwrap(data, "region", "rtc_region")
        return cls(
            id=payload.get("id"),
            name=payload.get("name"),
            optimal=payload.get("optimal"),
            deprecated=payload.get("deprecated"),
            emoji=payload.get("emoji"),
            raw_data=data,
        )


@dataclass(slots=True)
class CallState:
    """Private-channel call snapshot from Call Create or Call Update.

    The legacy active field has no documented wire equivalent and remains None
    unless explicitly supplied by a compatibility payload.

    Attributes:
        channel_id: Channel identity retained from the payload or operation context.
        region: Region used by this operation.
        active: Active used by this operation.
        message_id: ID of the call message.
        ringing: Recipients currently being rung.
        voice_states: Participant voice states as received; internal routing fields are opaque.
        recipients: All channel recipients, present only for a pulled snapshot.
        created_at: Call creation time in Unix milliseconds, when supplied.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    channel_id: int | None = None
    region: str | None = None
    active: bool | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    message_id: int | None = None
    ringing: list[int] = field(default_factory=list)
    voice_states: list[dict[str, Any]] = field(default_factory=list)
    recipients: list[int] | None = None
    created_at: int | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> CallState:
        """Build a CallState from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed CallState instance.
        """
        payload = _unwrap(data, "call", "state")
        return cls(
            channel_id=_maybe_int(payload.get("channel_id")),
            region=payload.get("region") or payload.get("rtc_region"),
            active=payload.get("active"),
            message_id=_maybe_int(payload.get("message_id")),
            ringing=[int(item) for item in payload.get("ringing", [])],
            voice_states=list(payload.get("voice_states", [])),
            recipients=[int(item) for item in payload["recipients"]]
            if "recipients" in payload
            else None,
            created_at=payload.get("created_at"),
            raw_data=data,
        )


@dataclass(slots=True)
class VoiceDebugSession:
    """Compatibility view of caller-supplied voice debug metadata.

    The current platform documentation defines no complete response matching
    these convenience fields. Missing values stay None and raw_data preserves
    the original payload; this class does not imply an implemented HTTP workflow.

    Attributes:
        channel_id: Channel identity retained from the payload or operation context.
        enabled: Whether command invocation is currently permitted.
        session_id: Identity of the session used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    channel_id: int | None = None
    enabled: bool | None = None
    session_id: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> VoiceDebugSession:
        """Build a VoiceDebugSession from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed VoiceDebugSession instance.
        """
        payload = _unwrap(data, "session", "voice_debug_session")
        return cls(
            channel_id=_maybe_int(payload.get("channel_id")),
            enabled=payload.get("enabled")
            if "enabled" in payload
            else payload.get("active"),
            session_id=payload.get("session_id") or payload.get("id"),
            raw_data=data,
        )


@dataclass(slots=True)
class SlowmodeState:
    """A Fluxer channel slowmode state response.

    Attributes:
        channel_id: Channel identity retained from the payload or operation context.
        interval: Interval used by this operation.
        next_allowed_at: Next allowed at used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        rate_limit_per_user: The configured slowmode interval in seconds, or `0` when slowmode is disabled.
        retry_after_ms: The remaining delay in milliseconds before the user can send.
        next_send_allowed_at: The next permitted send time, or null when no delay applies.
        can_bypass: Whether the user bypasses slowmode through BYPASS_SLOWMODE.
    """

    channel_id: int | None = None
    interval: int | None = None
    next_allowed_at: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    rate_limit_per_user: int | None = None
    retry_after_ms: int | None = None
    next_send_allowed_at: str | None = None
    can_bypass: bool | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> SlowmodeState:
        """Build a SlowmodeState from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed SlowmodeState instance.
        """
        payload = _unwrap(data, "slowmode", "state")
        return cls(
            channel_id=_maybe_int(payload.get("channel_id")),
            interval=_maybe_int(
                payload.get("interval", payload.get("rate_limit_per_user"))
            ),
            next_allowed_at=payload.get("next_send_allowed_at"),
            rate_limit_per_user=payload.get("rate_limit_per_user"),
            retry_after_ms=payload.get("retry_after_ms"),
            next_send_allowed_at=payload.get("next_send_allowed_at"),
            can_bypass=payload.get("can_bypass"),
            raw_data=data,
        )


__all__ = (
    "AttachmentUploadSpec",
    "AttachmentUploadPart",
    "AttachmentUpload",
    "AttachmentUploadPlan",
    "CompletedAttachmentUpload",
    "CompletedAttachmentUploadList",
    "SavedMessage",
    "ScheduledMessage",
    "Mention",
    "Relationship",
    "FavoriteMeme",
    "SearchResult",
    "SearchIndexing",
    "parse_search_response",
    "ReadState",
    "FavoriteGif",
    "GiftCode",
    "PackSummary",
    "PackDashboardSection",
    "PackDashboard",
    "EntranceSound",
    "EntranceSoundSelection",
    "EntranceSoundLibrary",
    "Theme",
    "BanEntry",
    "DiscoveryGuild",
    "VanityUrl",
    "BulkOperationResult",
    "DiscoveryApplication",
    "DiscoveryStatus",
    "GuildTransferResult",
    "BulkEmojiResult",
    "BulkStickerResult",
    "Team",
    "AppInfo",
    "AuthSession",
    "MFAState",
    "WebAuthnCredential",
    "UserSettings",
    "UserConnection",
    "AuthorizedIP",
    "DataHarvest",
    "CallEligibility",
    "RTCRegion",
    "CallState",
    "VoiceDebugSession",
    "SlowmodeState",
    "SearchScope",
    "SearchAuthorType",
    "SearchContentType",
    "SearchEmbedType",
    "SearchSortBy",
    "SearchSortOrder",
    "SearchResponse",
)
