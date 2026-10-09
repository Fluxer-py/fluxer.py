"""Asset helpers and public types for fluxer.py.

An :class:`Asset` is an image served by the Fluxer Media Proxy, such as an
avatar, a guild icon, a banner, an emoji, or a sticker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace as _dc_replace
from typing import IO, Any
from urllib.parse import urlencode, urlsplit

import aiohttp

from ._endpoints import asset_url
from .file import File

#: Output formats the Media Proxy accepts for an image asset.
VALID_ASSET_FORMATS = frozenset({"png", "jpg", "jpeg", "webp", "gif", "apng", "avif"})
#: Formats that have no animation.
VALID_STATIC_FORMATS = VALID_ASSET_FORMATS - {"gif", "apng"}


async def _download(url: str) -> bytes:
    """Download a public URL without account authentication.

    Args:
        url: URL to fetch.

    Returns:
        The complete response body.

    Raises:
        aiohttp.ClientError: The download fails or returns an HTTP error.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()


def _write(
    data: bytes, fp: str | os.PathLike[str] | IO[bytes], seek_begin: bool
) -> int:
    """Write bytes to a path or a binary file object.

    Args:
        data: Bytes to write.
        fp: Destination path, or a binary file object opened for writing.
        seek_begin: For a file object, rewind it to the start after writing.

    Returns:
        Number of bytes written.
    """
    if isinstance(fp, (str, os.PathLike)):
        with open(fp, "wb") as handle:
            return handle.write(data)
    written = fp.write(data)
    if seek_begin:
        fp.seek(0)
    return written


@dataclass(frozen=True, slots=True)
class Asset:
    """An image served by the Fluxer Media Proxy.

    Models expose assets as properties, for example ``user.avatar``,
    ``member.display_avatar``, ``guild.icon``, or ``emoji.asset``. Use
    :attr:`url` for the address, the ``with_*`` methods for a resized or
    re-encoded variant, and :meth:`read`, :meth:`save`, or :meth:`to_file` to
    download it.

    Default avatars come from the instance's static CDN, which applies no
    transformation, so the ``with_*`` methods return them unchanged.

    Attributes:
        url: Absolute URL of the asset, including any size or format options.
        key: The image hash, or the emoji or sticker ID.
    """

    _http: Any
    _service: str
    _path: str
    _ext: str
    _key: str
    _animated: bool = False
    _query: tuple[tuple[str, str], ...] = ()
    _transformable: bool = True

    # -- Construction (one place for every Media Proxy path) --

    @classmethod
    def _from_hash(cls, http: Any, path: str, image_hash: str) -> Asset:
        animated = image_hash.startswith("a_")
        return cls(
            http,
            "media",
            f"{path}/{image_hash}",
            "gif" if animated else "png",
            image_hash,
            animated,
        )

    @classmethod
    def _from_avatar(cls, http: Any, user_id: int, image_hash: str) -> Asset:
        return cls._from_hash(http, f"avatars/{user_id}", image_hash)

    @classmethod
    def _from_default_avatar(cls, http: Any, user_id: int) -> Asset:
        index = str(int(user_id) % 6)
        return cls(
            http, "static_cdn", f"avatars/{index}", "png", index, _transformable=False
        )

    @classmethod
    def _from_banner(cls, http: Any, owner_id: int, image_hash: str) -> Asset:
        return cls._from_hash(http, f"banners/{owner_id}", image_hash)

    @classmethod
    def _from_guild_image(
        cls, http: Any, kind: str, guild_id: int, image_hash: str
    ) -> Asset:
        return cls._from_hash(http, f"{kind}/{guild_id}", image_hash)

    @classmethod
    def _from_guild_member_avatar(
        cls, http: Any, guild_id: int | None, user_id: int, image_hash: str
    ) -> Asset:
        return cls._from_hash(
            http, f"guilds/{guild_id}/users/{user_id}/avatars", image_hash
        )

    @classmethod
    def _from_guild_member_banner(
        cls, http: Any, guild_id: int | None, user_id: int, image_hash: str
    ) -> Asset:
        return cls._from_hash(
            http, f"guilds/{guild_id}/users/{user_id}/banners", image_hash
        )

    @classmethod
    def _from_emoji(cls, http: Any, emoji_id: int, animated: bool) -> Asset:
        return cls._from_id(http, "emojis", emoji_id, animated)

    @classmethod
    def _from_sticker(cls, http: Any, sticker_id: int, animated: bool) -> Asset:
        return cls._from_id(http, "stickers", sticker_id, animated)

    @classmethod
    def _from_id(cls, http: Any, kind: str, item_id: int, animated: bool) -> Asset:
        # Emoji and sticker paths carry no "a_" hash, so animation is opt-in.
        query = (("animated", "true"),) if animated else ()
        return cls(
            http, "media", f"{kind}/{item_id}", "webp", str(item_id), animated, query
        )

    # -- Public API --

    @property
    def url(self) -> str:
        """Absolute URL of the asset, including any size or format options.

        Returns:
            The asset URL.

        Raises:
            RuntimeError: The owning model is not bound to an initialized client.
        """
        base = asset_url(self._http, self._service, f"{self._path}.{self._ext}")
        return f"{base}?{urlencode(self._query)}" if self._query else base

    @property
    def key(self) -> str:
        """The image hash, or the emoji or sticker ID.

        Returns:
            The identifying key of the image.
        """
        return self._key

    def is_animated(self) -> bool:
        """Return whether the asset is animated.

        Returns:
            True for an animated avatar, icon, or banner (``a_`` hash) or an
            animated emoji or sticker.
        """
        return self._animated

    def _with_query(self, name: str, value: str) -> Asset:
        query = tuple((k, v) for k, v in self._query if k != name) + ((name, value),)
        return _dc_replace(self, _query=query)

    def with_size(self, size: int) -> Asset:
        """Return a variant at the requested size.

        The Media Proxy rounds the size up to its next supported step and keeps it
        within the limits of the image kind.

        Args:
            size: Requested edge length in pixels.

        Returns:
            A new asset, or this asset when it cannot be transformed.

        Raises:
            ValueError: ``size`` is not a positive integer.
        """
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError("size must be a positive integer")
        if not self._transformable:
            return self
        return self._with_query("size", str(size))

    def with_format(self, format: str) -> Asset:
        """Return a variant in another output format.

        Args:
            format: One of ``png``, ``jpg``, ``jpeg``, ``webp``, ``gif``, ``apng``, or ``avif``.

        Returns:
            A new asset, or this asset when it cannot be transformed.

        Raises:
            ValueError: ``format`` is not a supported output format.
        """
        fmt = format.lower()
        if fmt not in VALID_ASSET_FORMATS:
            raise ValueError(f"format must be one of {sorted(VALID_ASSET_FORMATS)}")
        if not self._transformable:
            return self
        return _dc_replace(self, _ext=fmt)

    def with_static_format(self, format: str) -> Asset:
        """Return a variant in a static format, leaving animated assets unchanged.

        Args:
            format: One of ``png``, ``jpg``, ``jpeg``, ``webp``, or ``avif``.

        Returns:
            A new asset for a static image, or this asset when it is animated
            or cannot be transformed.

        Raises:
            ValueError: ``format`` is not a supported static format.
        """
        fmt = format.lower()
        if fmt not in VALID_STATIC_FORMATS:
            raise ValueError(f"format must be one of {sorted(VALID_STATIC_FORMATS)}")
        if self._animated:
            return self
        return self.with_format(fmt)

    def replace(
        self,
        *,
        size: int | None = None,
        format: str | None = None,
        static_format: str | None = None,
    ) -> Asset:
        """Return a variant with several options changed at once.

        Args:
            size: Requested edge length in pixels.
            format: Output format for every asset.
            static_format: Output format applied only when the asset is not animated.

        Returns:
            A new asset with the requested options.

        Raises:
            ValueError: An option is invalid.
        """
        asset = self
        if format is not None:
            asset = asset.with_format(format)
        if static_format is not None:
            asset = asset.with_static_format(static_format)
        if size is not None:
            asset = asset.with_size(size)
        return asset

    async def read(self) -> bytes:
        """Download the asset.

        Returns:
            The image bytes.

        Raises:
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        return await _download(self.url)

    async def save(
        self, fp: str | os.PathLike[str] | IO[bytes], *, seek_begin: bool = True
    ) -> int:
        """Download the asset into a file.

        Args:
            fp: Destination path (created or overwritten), or a binary file object.
            seek_begin: For a file object, rewind it to the start after writing.

        Returns:
            Number of bytes written.

        Raises:
            aiohttp.ClientError: The download fails or returns an HTTP error.
            OSError: The destination cannot be opened or written.
        """
        return _write(await self.read(), fp, seek_begin)

    async def to_file(
        self,
        *,
        filename: str | None = None,
        spoiler: bool = False,
        description: str | None = None,
    ) -> File:
        """Download the asset as a :class:`File` ready to attach to a message.

        Args:
            filename: Attachment filename; defaults to the asset's file name.
            spoiler: Whether to mark the attachment as a spoiler.
            description: Alternative text for the attachment.

        Returns:
            A file holding the downloaded bytes.

        Raises:
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        name = filename or f"{self._path.rsplit('/', 1)[-1]}.{self._ext}"
        return File(
            await self.read(), filename=name, spoiler=spoiler, description=description
        )

    def __eq__(self, other: object) -> bool:
        """Compare two assets by the image and options they address.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether both assets address the same URL.
        """
        if not isinstance(other, Asset):
            return NotImplemented
        return self._identity() == other._identity()

    def __hash__(self) -> int:
        """Hash by the image and options the asset addresses.

        Returns:
            The identity hash.
        """
        return hash(self._identity())

    def _identity(self) -> tuple[Any, ...]:
        return (self._service, self._path, self._ext, self._query)

    def __repr__(self) -> str:
        """Return a developer-facing representation.

        Returns:
            The asset kind and key.
        """
        return f"<Asset path={self._path}.{self._ext!s} animated={self._animated}>"

    def __str__(self) -> str:
        """Return the asset URL.

        Returns:
            The asset URL.
        """
        return self.url


class _AssetBacked:
    """Download helpers for models whose image is a single :class:`Asset`."""

    __slots__ = ()

    def _require_asset(self) -> Asset:
        raise NotImplementedError

    async def read(self) -> bytes:
        """Download the image.

        Returns:
            The image bytes.

        Raises:
            ValueError: The model has no downloadable image.
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        return await self._require_asset().read()

    async def save(
        self, fp: str | os.PathLike[str] | IO[bytes], *, seek_begin: bool = True
    ) -> int:
        """Download the image into a file.

        Args:
            fp: Destination path (created or overwritten), or a binary file object.
            seek_begin: For a file object, rewind it to the start after writing.

        Returns:
            Number of bytes written.

        Raises:
            ValueError: The model has no downloadable image.
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        return await self._require_asset().save(fp, seek_begin=seek_begin)

    async def to_file(
        self,
        *,
        filename: str | None = None,
        spoiler: bool = False,
        description: str | None = None,
    ) -> File:
        """Download the image as a :class:`File` ready to attach to a message.

        Args:
            filename: Attachment filename; defaults to the image's file name.
            spoiler: Whether to mark the attachment as a spoiler.
            description: Alternative text for the attachment.

        Returns:
            A file holding the downloaded bytes.

        Raises:
            ValueError: The model has no downloadable image.
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        return await self._require_asset().to_file(
            filename=filename, spoiler=spoiler, description=description
        )


class _GuildImages:
    """Asset properties shared by guild models that carry image hashes."""

    __slots__ = ()

    id: int
    icon_hash: str | None
    banner_hash: str | None
    splash_hash: str | None
    embed_splash_hash: str | None
    _http: Any

    def _guild_image(self, kind: str, image_hash: str | None) -> Asset | None:
        if not image_hash:
            return None
        return Asset._from_guild_image(self._http, kind, self.id, image_hash)

    @property
    def icon(self) -> Asset | None:
        """The guild icon, or None when the guild has none.

        Returns:
            The icon asset, when set.
        """
        return self._guild_image("icons", self.icon_hash)

    @property
    def banner(self) -> Asset | None:
        """The guild banner, or None when the guild has none.

        Returns:
            The banner asset, when set.
        """
        return self._guild_image("banners", self.banner_hash)

    @property
    def splash(self) -> Asset | None:
        """The invite splash image, or None when the guild has none.

        Returns:
            The splash asset, when set.
        """
        return self._guild_image("splashes", self.splash_hash)

    @property
    def embed_splash(self) -> Asset | None:
        """The embedded invite splash image, or None when the guild has none.

        Returns:
            The embed splash asset, when set.
        """
        return self._guild_image("embed-splashes", self.embed_splash_hash)

    @property
    def icon_url(self) -> str | None:
        """URL of :attr:`icon`, or None.

        Returns:
            The icon URL, when set.
        """
        asset = self.icon
        return asset.url if asset else None

    @property
    def banner_url(self) -> str | None:
        """URL of :attr:`banner`, or None.

        Returns:
            The banner URL, when set.
        """
        asset = self.banner
        return asset.url if asset else None

    @property
    def splash_url(self) -> str | None:
        """URL of :attr:`splash`, or None.

        Returns:
            The splash URL, when set.
        """
        asset = self.splash
        return asset.url if asset else None

    @property
    def embed_splash_url(self) -> str | None:
        """URL of :attr:`embed_splash`, or None.

        Returns:
            The embed splash URL, when set.
        """
        asset = self.embed_splash
        return asset.url if asset else None


def _url_filename(url: str) -> str:
    """Return the last path segment of a URL, for default attachment names."""
    return urlsplit(url).path.rsplit("/", 1)[-1] or "file"


__all__ = ("Asset",)
