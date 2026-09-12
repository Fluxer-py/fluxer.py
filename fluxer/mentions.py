"""Mentions helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AllowedMentions:
    """Allowed mention helper for Fluxer message payloads.

    Attributes:
        everyone: Everyone used by this operation.
        users: Users used by this operation.
        roles: Assigned role IDs; supplying the collection replaces the assignment.
        replied_user: Replied user used by this operation.
    """

    everyone: bool = True
    users: bool | list[int | str] = True
    roles: bool | list[int | str] = True
    replied_user: bool = True

    @classmethod
    def none(cls) -> "AllowedMentions":
        """None.

        Returns:
            The result of this operation.
        """
        return cls(everyone=False, users=False, roles=False, replied_user=False)

    @classmethod
    def all(cls) -> "AllowedMentions":
        """All.

        Returns:
            The result of this operation.
        """
        return cls()

    def to_dict(self) -> dict[str, Any]:
        """Serialize this object's supported fields to a dictionary.

        Returns:
            The serialized representation with supported fields preserved.
        """
        parse: list[str] = []
        data: dict[str, Any] = {"replied_user": self.replied_user}
        if self.everyone:
            parse.append("everyone")
        if self.users is True:
            parse.append("users")
        elif self.users:
            data["users"] = [str(user_id) for user_id in self.users]
        if self.roles is True:
            parse.append("roles")
        elif self.roles:
            data["roles"] = [str(role_id) for role_id in self.roles]
        data["parse"] = parse
        return data


__all__ = ("AllowedMentions",)
