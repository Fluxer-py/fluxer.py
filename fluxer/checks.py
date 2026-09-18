"""Convenience checks for commands using Fluxer roles and permissions."""

from __future__ import annotations

from typing import Any, Callable

from .enums import Permissions
from .ext.commands.core import has_permissions, has_role as _has_role


def has_role(
    name: str | None = None, id: int | str | None = None
) -> Callable[[Any], Any]:
    """Require a role identified by its name or ID.

    Args:
        name: Case-sensitive role name.
        id: Role ID, supplied as an integer or decimal string.

    Returns:
        A command check decorator.
    """
    if (name is None) == (id is None):
        raise ValueError("Specify exactly one of name or id")
    return _has_role(int(id) if id is not None else str(name))


def has_permission(permission: Permissions) -> Callable[[Any], Any]:
    """Require every bit in a Fluxer permission mask.

    Args:
        permission: One or more combined permission flags.

    Returns:
        A command check decorator.
    """
    if not isinstance(permission, Permissions):
        raise TypeError("permission must be a Permissions value")
    known_mask = sum(int(flag) for flag in Permissions)
    if int(permission) & ~known_mask:
        raise ValueError("permission contains unknown bits")
    flags = {
        str(flag.name).lower(): True
        for flag in Permissions
        if flag.value and flag.value & (flag.value - 1) == 0 and permission & flag
    }
    return has_permissions(**flags)


__all__ = ("has_role", "has_permission")
