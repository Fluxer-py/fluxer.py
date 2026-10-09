"""Attachment helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import IO, Any

from ..asset import _download, _url_filename, _write
from ..file import File
from ..flags import AttachmentFlags


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
        flags: Fluxer attachment flag wrapper retaining the raw mask.
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
    flags: AttachmentFlags = field(default_factory=AttachmentFlags)
    nsfw: bool | None = None
    duration: int | None = None
    waveform: str | None = None
    expires_at: str | None = None
    expired: bool | None = None

    def __post_init__(self) -> None:
        """Normalize an integer flag mask supplied to the constructor."""
        self.flags = AttachmentFlags(self.flags)

    def is_spoiler(self) -> bool:
        """Return whether Fluxer presents this attachment as a spoiler.

        Returns:
            Whether the spoiler flag is set.
        """
        return self.flags.is_spoiler

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
            flags=AttachmentFlags(data.get("flags", 0)),
            nsfw=data.get("nsfw", None),
            duration=data.get("duration", None),
            waveform=data.get("waveform", None),
            expires_at=data.get("expires_at", None),
            expired=data.get("expired", None),
        )

    def _download_url(self, use_cached: bool) -> str:
        url = self.proxy_url if use_cached and self.proxy_url else self.url
        if not url:
            raise ValueError("The attachment has no URL to download")
        return url

    async def read(self, *, use_cached: bool = False) -> bytes:
        """Download the attachment from the URL Fluxer issued for it.

        Args:
            use_cached: Download ``proxy_url`` (the Media Proxy copy) instead of ``url``.

        Returns:
            The attachment bytes.

        Raises:
            ValueError: The attachment has no URL.
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        return await _download(self._download_url(use_cached))

    async def save(
        self,
        fp: str | os.PathLike[str] | IO[bytes],
        *,
        seek_begin: bool = True,
        use_cached: bool = False,
    ) -> int:
        """Download the attachment into a file.

        Args:
            fp: Destination path (created or overwritten), or a binary file object.
            seek_begin: For a file object, rewind it to the start after writing.
            use_cached: Download ``proxy_url`` instead of ``url``.

        Returns:
            Number of bytes written.

        Raises:
            ValueError: The attachment has no URL.
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        return _write(await self.read(use_cached=use_cached), fp, seek_begin)

    async def to_file(
        self,
        *,
        filename: str | None = None,
        spoiler: bool | None = None,
        description: str | None = None,
        use_cached: bool = False,
    ) -> File:
        """Download the attachment as a :class:`File` ready to send again.

        Args:
            filename: Attachment filename; defaults to this attachment's filename.
            spoiler: Whether to mark it as a spoiler; defaults to this attachment's state.
            description: Alternative text; defaults to this attachment's description.
            use_cached: Download ``proxy_url`` instead of ``url``.

        Returns:
            A file holding the downloaded bytes.

        Raises:
            ValueError: The attachment has no URL.
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        data = await self.read(use_cached=use_cached)
        return File(
            data,
            filename=filename or self.filename or _url_filename(self.url or ""),
            spoiler=self.is_spoiler() if spoiler is None else spoiler,
            description=self.description if description is None else description,
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
            value = int(self.flags) if key == "flags" else getattr(self, key)
            if value is not None:
                data[key] = value
        return data


__all__ = ("Attachment",)
