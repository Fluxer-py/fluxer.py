"""Attachment helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Attachment:
    """Represents a file attached to a Fluxer message.

    Attributes:
        id: Identity of the object used by this operation.
        filename: Filename presented to the server and recipients.
        size: Size used by this operation.
        url: Absolute destination or resource URL.
        proxy_url: Proxy url used by this operation.
        width: Width used by this operation.
        height: Height used by this operation.
        content_type: Content type used by this operation.
        description: Descriptive text associated with this object.
        ephemeral: Ephemeral used by this operation.
        title: Title used by this operation.
        content_hash: Content hash used by this operation.
        placeholder: Placeholder used by this operation.
        flags: Bit mask governing the object's documented flags.
        nsfw: Nsfw used by this operation.
        duration: Duration used by this operation.
        waveform: Waveform used by this operation.
        expires_at: Expires at used by this operation.
        expired: Expired used by this operation.
    """

    id: int
    filename: str
    size: int
    url: str | None
    proxy_url: str | None = None
    width: int | None = None
    height: int | None = None
    content_type: str | None = None
    description: str | None = None
    ephemeral: bool = False

    title: str | None = None
    content_hash: str | None = None
    placeholder: str | None = None
    flags: int = 0
    nsfw: bool | None = None
    duration: int | None = None
    waveform: str | None = None
    expires_at: str | None = None
    expired: bool | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> Attachment:
        """Build a Attachment from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed Attachment instance.
        """
        return cls(
            id=int(data["id"]),
            filename=data["filename"],
            size=int(data["size"]),
            url=data["url"],
            proxy_url=data.get("proxy_url"),
            width=int(data["width"]) if data.get("width") is not None else None,
            height=int(data["height"]) if data.get("height") is not None else None,
            content_type=data.get("content_type"),
            description=data.get("description"),
            ephemeral=data.get("ephemeral", False),
            title=data.get("title", None),
            content_hash=data.get("content_hash", None),
            placeholder=data.get("placeholder", None),
            flags=data.get("flags", 0),
            nsfw=data.get("nsfw", None),
            duration=data.get("duration", None),
            waveform=data.get("waveform", None),
            expires_at=data.get("expires_at", None),
            expired=data.get("expired", None),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the Attachment to a dictionary for API requests.

        Returns:
            The serialized representation with supported fields preserved.
        """
        data: dict[str, Any] = {
            "id": str(self.id),
            "filename": self.filename,
            "size": self.size,
            "url": self.url,
        }
        if self.proxy_url is not None:
            data["proxy_url"] = self.proxy_url
        if self.width is not None:
            data["width"] = self.width
        if self.height is not None:
            data["height"] = self.height
        if self.content_type is not None:
            data["content_type"] = self.content_type
        if self.description is not None:
            data["description"] = self.description

        for key in (
            "title",
            "content_hash",
            "placeholder",
            "flags",
            "nsfw",
            "duration",
            "waveform",
            "expires_at",
            "expired",
        ):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


__all__ = ("Attachment",)
