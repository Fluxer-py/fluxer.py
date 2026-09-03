from __future__ import annotations

from .enums import Permissions


class PermissionOverwrite:
    def __init__(self, **kwargs: bool | None) -> None:
        self._values = dict(kwargs)

    def pair(self) -> tuple[Permissions, Permissions]:
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
