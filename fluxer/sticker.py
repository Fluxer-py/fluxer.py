"""Sticker helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .models.user import User

if TYPE_CHECKING:
    from .http import HTTPClient


@dataclass(slots=True)
class Sticker:
    """Sticker data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
        name: Name to assign or resolve in this operation.
        guild_id: Guild identity retained from the payload or operation context.
        description: Sticker description, or an empty string when none is stored.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        tags: Tags used by this operation.
        animated: Animated used by this operation.
        user: User object or identity used by the operation.
    """

    id: int
    name: str
    guild_id: int | None = None
    description: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)
    tags: list[str] = field(default_factory=list)
    animated: bool = False
    user: User | None = None
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        guild_id: int | None = None,
    ) -> Sticker:
        """Build a Sticker from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.
            guild_id: Identity of the guild used by this operation.

        Returns:
            A parsed Sticker instance.
        """
        return cls(
            id=int(data["id"]),
            name=data.get("name", ""),
            guild_id=guild_id
            if guild_id is not None
            else (int(data["guild_id"]) if data.get("guild_id") is not None else None),
            description=data.get("description", ""),
            tags=list(data.get("tags", [])),
            animated=data.get("animated", False),
            user=User.from_data(data["user"], http)
            if data.get("user") is not None
            else None,
            raw_data=dict(data),
            _http=http,
        )

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete.

        Args:
            reason: Audit-log reason forwarded when the underlying operation supports it.

        Returns:
            None.
        """
        if self._http is None or self.guild_id is None:
            raise RuntimeError("Sticker is not bound to a guild HTTP client")
        await self._http.delete_guild_sticker(self.guild_id, self.id, reason=reason)

    def __str__(self) -> str:
        """Return the object's user-facing text representation.

        Returns:
            The result of this operation.
        """
        return self.name


__all__ = ("Sticker",)
