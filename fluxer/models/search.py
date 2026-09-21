"""Message search request literals and response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from .._payload import maybe_int
from . import channel as channel_models
from .message import Message

if TYPE_CHECKING:
    from ..http import HTTPClient
    from .channel import Channel


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
        raw_messages = data.get("messages", data.get("results", []))
        raw_channels = data.get("channels") or []
        channels = [
            channel_models.Channel.from_data(item, http)
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
            total=maybe_int(total) or 0,
            hits_per_page=maybe_int(data.get("hits_per_page")) or 25,
            page=maybe_int(data.get("page")) or 1,
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


__all__ = (
    "SearchResult",
    "SearchIndexing",
    "parse_search_response",
    "SearchScope",
    "SearchAuthorType",
    "SearchContentType",
    "SearchEmbedType",
    "SearchSortBy",
    "SearchSortOrder",
    "SearchResponse",
)
