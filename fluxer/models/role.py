"""Role helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime
from .._types import UNSET, UnsetType

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class Role:
    """Represents a guild role.

    Attributes:
        id: Identity of the object used by this operation.
        name: Name to assign or resolve in this operation.
        color: Packed RGB colour value.
        hoist: Whether the role is displayed separately in member lists.
        position: Position used by this operation.
        permissions: Complete permission bit mask for the requested role operation.
        managed: Managed used by this operation.
        mentionable: Whether members may mention this role.
        hoist_position: Separate display position of a hoisted role, or None.
        guild_id: Guild identity retained from the payload or operation context.
        created_at: When this role was created (derived from Snowflake).
        mention: Return a string that mentions this role in a message.
        is_default: Whether this is the @everyone role.
    """

    id: int
    name: str
    color: int = 0  # RGB color value
    hoist: bool = False  # Whether role is displayed separately in member list
    position: int = 0  # Position in role hierarchy
    permissions: int = 0  # Permission bitfield
    managed: bool = False  # Whether role is managed by an integration
    mentionable: bool = False  # Whether role can be mentioned

    hoist_position: int | None = None

    # Guild reference
    guild_id: int | None = None

    # Back-reference (set after construction)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        guild_id: int | None = None,
    ) -> Role:
        """Create a Role from API data.

        Args:
            data: Role data from API
            http: HTTP client for making requests
            guild_id: Guild ID (may not be in data for some endpoints)

        Returns:
            A parsed Role instance.
        """
        return cls(
            id=int(data["id"]),
            name=data.get("name", ""),
            color=data.get("color", 0),
            hoist=data.get("hoist", False),
            hoist_position=data.get("hoist_position"),
            position=data.get("position", 0),
            permissions=int(data.get("permissions", 0)),
            managed=data.get("managed", False),
            mentionable=data.get("mentionable", False),
            guild_id=guild_id
            or (int(data["guild_id"]) if data.get("guild_id") else None),
            _http=http,
        )

    @property
    def created_at(self) -> datetime:
        """When this role was created (derived from Snowflake).

        Returns:
            The result of this operation.
        """
        return snowflake_to_datetime(self.id)

    @property
    def mention(self) -> str:
        """Return a string that mentions this role in a message.

        Returns:
            The result of this operation.
        """
        return f"<@&{self.id}>"

    @property
    def is_default(self) -> bool:
        """Whether this is the @everyone role.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.guild_id == self.id if self.guild_id else False

    async def edit(
        self,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int | None = None,
        hoist: bool | None = None,
        mentionable: bool | None = None,
        hoist_position: int | None | UnsetType = UNSET,
        reason: str | None = None,
    ) -> Role:
        """Edit this role.

        Args:
            name: New name
            permissions: New permissions bitfield
            color: New color
            hoist: Whether to display role separately
            mentionable: Whether role can be mentioned
            reason: Reason for audit log
            hoist_position: Separate display position for a hoisted role; None clears it.

        Returns:
            Updated Role object
        """
        if not self._http or not self.guild_id:
            raise RuntimeError("Cannot edit role without HTTPClient and guild_id")

        extra: dict[str, Any] = {}
        if not isinstance(hoist_position, UnsetType):
            extra["hoist_position"] = hoist_position
        data = await self._http.modify_guild_role(
            self.guild_id,
            self.id,
            name=name,
            permissions=permissions,
            color=color,
            hoist=hoist,
            mentionable=mentionable,
            reason=reason,
            **extra,
        )
        return Role.from_data(data, self._http, self.guild_id)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this role.

        Args:
            reason: Reason for audit log

        Returns:
            None.
        """
        if not self._http or not self.guild_id:
            raise RuntimeError("Cannot delete role without HTTPClient and guild_id")

        await self._http.delete_guild_role(self.guild_id, self.id, reason=reason)

    def __str__(self) -> str:
        """Return the object's user-facing text representation.

        Returns:
            The result of this operation.
        """
        return self.name

    def __eq__(self, other: object) -> bool:
        """Compare this object with another value using its identity semantics.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return isinstance(other, Role) and self.id == other.id

    def __hash__(self) -> int:
        """Return the hash used for identity-based collection lookup.

        Returns:
            The result of this operation.
        """
        return hash(self.id)

    def __lt__(self, other: object) -> bool:
        """Roles are ordered by position (higher position = higher in hierarchy).

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        if not isinstance(other, Role):
            return NotImplemented
        if self.guild_id != other.guild_id:
            raise ValueError("Cannot compare roles from different guilds")
        if self.id == other.id:
            return False
        if self.is_default:
            return True
        if other.is_default:
            return False
        return (self.position, -self.id) < (other.position, -other.id)


__all__ = ("Role",)
