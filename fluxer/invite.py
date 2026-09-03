from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

if False:
    pass


@dataclass(slots=True)
class Invite:
    code: str
    guild_id: int | None = None
    channel_id: int | None = None
    inviter_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)
    _http: Any | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: Any | None = None) -> "Invite":
        guild = data.get("guild") or data.get("guild_id")
        channel = data.get("channel") or data.get("channel_id")
        inviter = data.get("inviter") or data.get("inviter_id")
        return cls(
            code=data.get("code") or data.get("invite_code") or "",
            guild_id=int(guild["id"] if isinstance(guild, dict) else guild)
            if guild
            else None,
            channel_id=int(channel["id"] if isinstance(channel, dict) else channel)
            if channel
            else None,
            inviter_id=int(inviter["id"] if isinstance(inviter, dict) else inviter)
            if inviter
            else None,
            raw_data=data,
            _http=http,
        )

    @property
    def url(self) -> str:
        return f"https://fluxer.app/invite/{self.code}"

    async def delete(self) -> None:
        if self._http is None:
            raise RuntimeError("Invite is not bound to an HTTP client")
        await self._http.delete_invite(self.code)

    def __str__(self) -> str:
        return self.url
