"""Embed helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Embed:
    """Builder for rich embed objects.

    Usage:
        embed = Embed(title="Hello", description="World", color=0x5865F2)
        embed.add_field(name="Field 1", value="Value 1")
        embed.set_footer(text="Footer text")
        await channel.send(embed=embed)

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
    footer: dict[str, Any] | None = None
    image: dict[str, Any] | None = None
    thumbnail: dict[str, Any] | None = None
    author: dict[str, Any] | None = None
    fields: list[dict[str, Any]] = field(default_factory=list)

    type: str | None = None
    provider: dict[str, Any] | None = None
    video: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    nsfw: bool | None = None
    html: str | None = None
    html_width: int | None = None
    html_height: int | None = None
    children: list[dict[str, Any]] | None = None

    def set_footer(self, *, text: str, icon_url: str | None = None) -> Embed:
        """Replace embed footer text and its optional icon.

        Args:
            text: Text to format, parse, or display.
            icon_url: Icon url used by this operation.

        Returns:
            This instance, allowing chained calls.
        """
        self.footer = {"text": text}
        if icon_url:
            self.footer["icon_url"] = icon_url
        return self

    def set_image(self, *, url: str) -> Embed:
        """Set the main image URL on this rich embed.

        Args:
            url: Absolute destination or resource URL.

        Returns:
            This instance, allowing chained calls.
        """
        self.image = {"url": url}
        return self

    def set_thumbnail(self, *, url: str) -> Embed:
        """Set the thumbnail URL on this rich embed.

        Args:
            url: Absolute destination or resource URL.

        Returns:
            This instance, allowing chained calls.
        """
        self.thumbnail = {"url": url}
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
        self.author = {"name": name}
        if url:
            self.author["url"] = url
        if icon_url:
            self.author["icon_url"] = icon_url
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
        self.fields.append({"name": name, "value": value, "inline": inline})
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for the API.

        Returns:
            The serialized representation with supported fields preserved.
        """
        d: dict[str, Any] = {}
        if self.title is not None:
            d["title"] = self.title
        if self.description is not None:
            d["description"] = self.description
        if self.url is not None:
            d["url"] = self.url
        if self.color is not None:
            d["color"] = self.color
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        if self.footer is not None:
            d["footer"] = self.footer
        if self.image is not None:
            d["image"] = self.image
        if self.thumbnail is not None:
            d["thumbnail"] = self.thumbnail
        if self.author is not None:
            d["author"] = self.author
        if self.fields:
            d["fields"] = self.fields
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
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Embed:
        """Build a Embed from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed Embed instance.
        """
        return cls(
            **{
                key: value
                for key, value in data.items()
                if key in cls.__dataclass_fields__
            }
        )

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


__all__ = ("Embed",)
