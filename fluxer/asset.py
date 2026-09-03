from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Asset:
    """Small URL-backed asset object."""

    url: str

    async def read(self) -> bytes:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(self.url) as response:
                response.raise_for_status()
                return await response.read()

    async def save(self, fp: str, *, seek_begin: bool = True) -> int:
        data = await self.read()
        with open(fp, "wb") as handle:
            return handle.write(data)

    def __str__(self) -> str:
        return self.url
