"""Asset helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Asset:
    """Small URL-backed asset object.

    Attributes:
        url: Absolute destination or resource URL.
    """

    url: str

    async def read(self) -> bytes:
        """Download the asset bytes without account authentication.

        Returns:
            The complete response body.

        Raises:
            aiohttp.ClientError: The download fails or returns an HTTP error.
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(self.url) as response:
                response.raise_for_status()
                return await response.read()

    async def save(self, fp: str, *, seek_begin: bool = True) -> int:
        """Download the asset and overwrite the destination file.

        Args:
            fp: Destination filesystem path to create or overwrite.
            seek_begin: Compatibility option; path-based saves close the written file.

        Returns:
            Number of bytes written.

        Raises:
            aiohttp.ClientError: The download fails or returns an HTTP error.
            OSError: The destination cannot be opened or written.
        """
        data = await self.read()
        with open(fp, "wb") as handle:
            return handle.write(data)

    def __str__(self) -> str:
        """Return the object's user-facing text representation.

        Returns:
            The result of this operation.
        """
        return self.url


__all__ = ("Asset",)
