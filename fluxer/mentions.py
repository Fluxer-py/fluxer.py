from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AllowedMentions:
    """Allowed mention helper for Fluxer message payloads."""

    everyone: bool = True
    users: bool | list[int | str] = True
    roles: bool | list[int | str] = True
    replied_user: bool = True

    @classmethod
    def none(cls) -> "AllowedMentions":
        return cls(everyone=False, users=False, roles=False, replied_user=False)

    @classmethod
    def all(cls) -> "AllowedMentions":
        return cls()

    def to_dict(self) -> dict[str, Any]:
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
