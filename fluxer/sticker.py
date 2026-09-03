from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Sticker:
    id: int
    name: str
    guild_id: int | None = None
    description: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)
    _http: Any | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: Any | None = None) -> "Sticker":
        return cls(
            id=int(data["id"]),
            name=data.get("name", ""),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            description=data.get("description"),
            raw_data=data,
            _http=http,
        )

    async def delete(self, *, reason: str | None = None) -> None:
        if self._http is None or self.guild_id is None:
            raise RuntimeError("Sticker is not bound to a guild HTTP client")
        await self._http.delete_guild_sticker(self.guild_id, self.id, reason=reason)

    def __str__(self) -> str:
        return self.name
