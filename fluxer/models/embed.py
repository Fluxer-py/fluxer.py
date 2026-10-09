"""Embed helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, TypeVar

_T = TypeVar("_T")


def _known(cls: type[_T], data: dict[str, Any]) -> _T:
    """Build a dataclass from the payload keys it declares, ignoring the rest."""
    names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    return cls(**{key: value for key, value in data.items() if key in names})


def _dump(value: Any) -> dict[str, Any]:
    """Serialize an embed part, dropping unset (None) keys."""
    if isinstance(value, dict):
        return value
    return {
        f.name: getattr(value, f.name)
        for f in fields(value)
        if getattr(value, f.name) is not None
    }


@dataclass(slots=True)
class EmbedAuthor:
    """Author block of an embed.

    An embed without an author has an empty EmbedAuthor: it is falsy and every
    attribute is None, so ``embed.author.name`` never raises.

    Attributes:
        name: Author name.
        url: Link opened from the author name.
        icon_url: Author icon URL.
        proxy_icon_url: Media-proxy URL of the author icon, set on received embeds.
    """

    name: str | None = None
    url: str | None = None
    icon_url: str | None = None
    proxy_icon_url: str | None = None

    def __bool__(self) -> bool:
        """Return whether any field is set; an unset part is falsy.

        Returns:
            Whether the part carries any data.
        """
        return any(getattr(self, f.name) is not None for f in fields(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbedAuthor:
        """Build an EmbedAuthor from its decoded payload.

        Args:
            data: Embed author object.

        Returns:
            The parsed author.
        """
        return _known(cls, data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to an embed author object.

        Returns:
            The payload with unset fields omitted.
        """
        return _dump(self)


@dataclass(slots=True)
class EmbedFooter:
    """Footer block of an embed.

    An embed without a footer has an empty, falsy EmbedFooter whose attributes
    are all None.

    Attributes:
        text: Footer text.
        icon_url: Footer icon URL.
        proxy_icon_url: Media-proxy URL of the footer icon, set on received embeds.
    """

    text: str | None = None
    icon_url: str | None = None
    proxy_icon_url: str | None = None

    def __bool__(self) -> bool:
        """Return whether any field is set; an unset part is falsy.

        Returns:
            Whether the part carries any data.
        """
        return any(getattr(self, f.name) is not None for f in fields(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbedFooter:
        """Build an EmbedFooter from its decoded payload.

        Args:
            data: Embed footer object.

        Returns:
            The parsed footer.
        """
        return _known(cls, data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to an embed footer object.

        Returns:
            The payload with unset fields omitted.
        """
        return _dump(self)


@dataclass(slots=True)
class EmbedField:
    """A named field of an embed.

    Attributes:
        name: Field name.
        value: Field value.
        inline: Whether the field is displayed inline.
    """

    name: str
    value: str
    inline: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbedField:
        """Build an EmbedField from its decoded payload.

        Args:
            data: Embed field object.

        Returns:
            The parsed field.
        """
        return _known(cls, {"name": "", "value": "", **data})

    def to_dict(self) -> dict[str, Any]:
        """Serialize to an embed field object.

        Returns:
            The field payload.
        """
        return _dump(self)


@dataclass(slots=True)
class EmbedProvider:
    """Site that produced an unfurled embed.

    An embed without a provider has an empty, falsy EmbedProvider whose
    attributes are all None.

    Attributes:
        name: Provider name.
        url: Provider URL.
    """

    name: str | None = None
    url: str | None = None

    def __bool__(self) -> bool:
        """Return whether any field is set; an unset part is falsy.

        Returns:
            Whether the part carries any data.
        """
        return any(getattr(self, f.name) is not None for f in fields(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbedProvider:
        """Build an EmbedProvider from its decoded payload.

        Args:
            data: Embed provider object.

        Returns:
            The parsed provider.
        """
        return _known(cls, data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to an embed provider object.

        Returns:
            The payload with unset fields omitted.
        """
        return _dump(self)


@dataclass(slots=True)
class EmbedMedia:
    """Image, thumbnail, video, or audio attached to an embed.

    Media an embed does not have is an empty, falsy EmbedMedia whose attributes
    are all None.

    Attributes:
        url: Source URL.
        proxy_url: Media-proxy URL, set on received embeds.
        width: Width in pixels.
        height: Height in pixels.
        duration: Duration of video or audio media.
        description: Alternative text.
        content_type: MIME type of the media.
        content_hash: Hash of the media content.
        placeholder: Placeholder shown while the media loads.
        flags: Media flags.
    """

    url: str | None = None
    proxy_url: str | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    description: str | None = None
    content_type: str | None = None
    content_hash: str | None = None
    placeholder: str | None = None
    flags: int | None = None

    def __bool__(self) -> bool:
        """Return whether any field is set; an unset part is falsy.

        Returns:
            Whether the part carries any data.
        """
        return any(getattr(self, f.name) is not None for f in fields(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbedMedia:
        """Build an EmbedMedia from its decoded payload.

        Args:
            data: Embed media object.

        Returns:
            The parsed media.
        """
        return _known(cls, data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to an embed media object.

        Returns:
            The payload with unset fields omitted.
        """
        return _dump(self)


_PARTS: dict[str, Any] = {}


def _part(cls: Any, value: Any) -> Any:
    if value is None:
        return cls()
    return cls.from_dict(value) if isinstance(value, dict) else value


@dataclass
class Embed:
    """A rich embed: a builder for outgoing embeds and the parsed form of received ones.

    Usage:
        embed = Embed(title="Hello", description="World", color=0x5865F2)
        embed.add_field(name="Field 1", value="Value 1")
        embed.set_footer(text="Footer text")
        await channel.send(embed=embed)

    Nested parts are typed objects (``embed.author.name``, ``embed.fields[0].value``).
    A part the embed does not have is an empty, falsy object
    whose attributes are None, so ``embed.footer.text`` is None instead of
    raising. Test presence with ``if embed.footer:``. Assigning None or a dict
    to a part stores an empty part or the parsed part.

    Attributes:
        title: Embed title.
        description: Embed description.
        url: Embed destination URL.
        color: Embed colour.
        timestamp: Embed timestamp.
        footer: Embed footer.
        image: Main image.
        thumbnail: Thumbnail image.
        author: Embed author.
        fields: Embed fields.
        type: Embed type.
        provider: External provider.
        video: Video media.
        audio: Audio media.
        nsfw: Whether the embed contains explicit media.
        html: Sanitised oEmbed markup for a trusted specialised renderer.
        html_width: Preferred pixel width of the sanitised oEmbed markup.
        html_height: Preferred pixel height of the sanitised oEmbed markup.
        children: At most one nested unfurler-generated embed, which itself has no `children` field.
    """

    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    timestamp: str | None = None
    footer: EmbedFooter = field(default_factory=EmbedFooter)
    image: EmbedMedia = field(default_factory=EmbedMedia)
    thumbnail: EmbedMedia = field(default_factory=EmbedMedia)
    author: EmbedAuthor = field(default_factory=EmbedAuthor)
    fields: list[EmbedField] = field(default_factory=list)

    type: str | None = None
    provider: EmbedProvider = field(default_factory=EmbedProvider)
    video: EmbedMedia = field(default_factory=EmbedMedia)
    audio: EmbedMedia = field(default_factory=EmbedMedia)
    nsfw: bool | None = None
    html: str | None = None
    html_width: int | None = None
    html_height: int | None = None
    children: list[Embed] | None = None

    def __setattr__(self, name: str, value: Any) -> None:
        """Store nested parts as typed objects, including on later assignment.

        Args:
            name: Attribute name.
            value: New value; None or a dict is converted for part attributes.
        """
        part = _PARTS.get(name)
        if part is not None:
            value = _part(part, value)
        elif name == "fields":
            value = [_part(EmbedField, item) for item in value or []]
        elif name == "children" and value is not None:
            value = [_part(Embed, item) for item in value]
        object.__setattr__(self, name, value)

    def set_footer(self, *, text: str, icon_url: str | None = None) -> Embed:
        """Replace embed footer text and its optional icon.

        Args:
            text: Text to format, parse, or display.
            icon_url: Icon url used by this operation.

        Returns:
            This instance, allowing chained calls.
        """
        self.footer = EmbedFooter(text=text, icon_url=icon_url or None)
        return self

    def set_image(self, *, url: str) -> Embed:
        """Set the main image URL on this rich embed.

        Args:
            url: Absolute destination or resource URL.

        Returns:
            This instance, allowing chained calls.
        """
        self.image = EmbedMedia(url=url)
        return self

    def set_thumbnail(self, *, url: str) -> Embed:
        """Set the thumbnail URL on this rich embed.

        Args:
            url: Absolute destination or resource URL.

        Returns:
            This instance, allowing chained calls.
        """
        self.thumbnail = EmbedMedia(url=url)
        return self

    def set_author(
        self, *, name: str, url: str | None = None, icon_url: str | None = None
    ) -> Embed:
        """Replace embed author metadata.

        Args:
            name: Name to assign or resolve in this operation.
            url: Absolute destination or resource URL.
            icon_url: Icon url used by this operation.

        Returns:
            This instance, allowing chained calls.
        """
        self.author = EmbedAuthor(name=name, url=url or None, icon_url=icon_url or None)
        return self

    def add_field(self, *, name: str, value: str, inline: bool = False) -> Embed:
        """Append a named field to this embed in display order.

        Args:
            name: Name to assign or resolve in this operation.
            value: Value to convert, assign, or compare.
            inline: Inline used by this operation.

        Returns:
            This instance, allowing chained calls.
        """
        self.fields.append(EmbedField(name=name, value=value, inline=inline))
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for the API.

        Returns:
            The serialized representation with supported fields preserved.
        """
        d: dict[str, Any] = {}
        for key in ("title", "description", "url", "color", "timestamp"):
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        for key in ("footer", "image", "thumbnail", "author"):
            value = getattr(self, key)
            if value:
                d[key] = _dump(value)
        if self.fields:
            d["fields"] = [_dump(item) for item in self.fields]
        for key in (
            "type",
            "nsfw",
            "html",
            "html_width",
            "html_height",
        ):
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        for key in ("provider", "video", "audio"):
            value = getattr(self, key)
            if value:
                d[key] = _dump(value)
        if self.children is not None:
            d["children"] = [
                item.to_dict() if isinstance(item, Embed) else item
                for item in self.children
            ]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Embed:
        """Build a Embed from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed Embed instance.
        """
        return _known(cls, data)

    def _to_request_dict(self) -> dict[str, Any]:
        data = self.to_dict()
        for key in (
            "type",
            "provider",
            "video",
            "audio",
            "nsfw",
            "html",
            "html_width",
            "html_height",
            "children",
        ):
            data.pop(key, None)
        for key, allowed in {
            "author": {"name", "url", "icon_url"},
            "footer": {"text", "icon_url"},
            "image": {"url"},
            "thumbnail": {"url"},
        }.items():
            if key in data:
                data[key] = {
                    name: value for name, value in data[key].items() if name in allowed
                }
        return data


_PARTS.update(
    footer=EmbedFooter,
    author=EmbedAuthor,
    provider=EmbedProvider,
    image=EmbedMedia,
    thumbnail=EmbedMedia,
    video=EmbedMedia,
    audio=EmbedMedia,
)


__all__ = (
    "Embed",
    "EmbedAuthor",
    "EmbedField",
    "EmbedFooter",
    "EmbedMedia",
    "EmbedProvider",
)
