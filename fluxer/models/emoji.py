"""Emoji helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .user import User

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class Emoji:
    """Represents a custom emoji in a Fluxer guild.

    Attributes:
        id: Identity of the object used by this operation.
        name: Name to assign or resolve in this operation.
        animated: Whether the stored image is animated.
        guild_id: Guild identity retained from the payload or operation context.
        roles: Compatibility list; Fluxer expressions have no role restrictions.
        managed: Compatibility flag defaulting to False; not a Fluxer expression field.
        available: Compatibility flag defaulting to True; not a server availability guarantee.
        user: Uploader account when supplied by the guild expression list.
    """

    id: int
    name: str
    animated: bool = False
    guild_id: int | None = None
    roles: list[int] = field(default_factory=list)
    managed: bool = False
    available: bool = True

    user: User | None = None

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        guild_id: int | None = None,
    ) -> Emoji:
        """Build a Emoji from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.
            guild_id: Identity of the guild used by this operation.

        Returns:
            A parsed Emoji instance.
        """
        return cls(
            id=int(data["id"]),
            name=data.get("name", ""),
            animated=data.get("animated", False),
            guild_id=guild_id
            or (int(data["guild_id"]) if data.get("guild_id") else None),
            roles=[int(role_id) for role_id in data.get("roles", [])],
            managed=data.get("managed", False),
            available=data.get("available", True),
            user=User.from_data(data["user"], http)
            if data.get("user") is not None
            else None,
            _http=http,
        )

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this emoji from its guild.

        Args:
            reason: Reason for deletion (shows in audit log)

        Raises:
            Forbidden: You don't have permission to delete emojis
            NotFound: Emoji doesn't exist
            HTTPException: Deleting the emoji failed

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot delete emoji without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot delete emoji without guild_id")

        await self._http.delete_guild_emoji(self.guild_id, self.id, reason=reason)

    def __str__(self) -> str:
        """Return the object's user-facing text representation.

        Returns:
            The result of this operation.
        """
        return f"<{'a' if self.animated else ''}:{self.name}:{self.id}>"


__all__ = ("Emoji",)
