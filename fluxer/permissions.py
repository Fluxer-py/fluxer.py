"""Permission masks, overwrite serialization, and local effective-permission calculation.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from typing import Any

from .enums import Permissions


class PermissionOverwrite:
    """Local allow/deny builder using documented permission names.

    Attributes:
        pair: Return the separate allow and deny masks.
    """

    def __init__(self, **kwargs: bool | None) -> None:
        """Initialize the permission overwrite with the supplied configuration.

        Args:
            **kwargs: Additional options forwarded to the underlying operation.
        """
        for name, value in kwargs.items():
            if name.upper() not in Permissions.__members__:
                raise ValueError(f"Unknown permission: {name}")
            if value is not None and not isinstance(value, bool):
                raise TypeError("Permission overwrite values must be bool or None")
        self._values: dict[str, bool | None] = dict(kwargs)

    def pair(self) -> tuple[Permissions, Permissions]:
        """Return separate allow and deny permission masks.

        Returns:
            The result of this operation.
        """
        allow = Permissions(0)
        deny = Permissions(0)
        for name, value in self._values.items():
            perm = getattr(Permissions, name.upper(), None)
            if perm is None:
                continue
            if value is True:
                allow |= perm
            elif value is False:
                deny |= perm
        return allow, deny


def _effective_permissions(
    guild: dict[str, Any],
    member: dict[str, Any],
    roles: list[dict[str, Any]],
    user_id: int,
    channel: dict[str, Any] | None = None,
) -> Permissions:
    """Compute the documented role union and channel overwrite precedence."""
    guild_id = int(guild["id"])
    role_ids = {int(role_id) for role_id in member.get("roles", [])}
    mask = 0
    for role in roles:
        if int(role["id"]) == guild_id or int(role["id"]) in role_ids:
            mask |= int(role.get("permissions", 0))
    if user_id == int(guild["owner_id"]) or mask & Permissions.ADMINISTRATOR:
        return Permissions((1 << 64) - 1)
    if channel is None:
        return Permissions(mask)
    overwrites = channel.get("permission_overwrites", [])
    everyone = next(
        (
            item
            for item in overwrites
            if int(item["id"]) == guild_id and item["type"] == 0
        ),
        None,
    )
    if everyone is not None:
        mask = (mask & ~int(everyone.get("deny") or 0)) | int(
            everyone.get("allow") or 0
        )
    allow = deny = 0
    for item in overwrites:
        if (
            item["type"] == 0
            and int(item["id"]) in role_ids
            and int(item["id"]) != guild_id
        ):
            allow |= int(item.get("allow") or 0)
            deny |= int(item.get("deny") or 0)
    mask = (mask & ~deny) | allow
    individual = next(
        (
            item
            for item in overwrites
            if item["type"] == 1 and int(item["id"]) == user_id
        ),
        None,
    )
    if individual is not None:
        mask = (mask & ~int(individual.get("deny") or 0)) | int(
            individual.get("allow") or 0
        )
    return Permissions(mask)


__all__ = ("Permissions", "PermissionOverwrite")
