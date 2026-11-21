"""Allowed mention policies for outgoing messages.

``AllowedMentions`` matches discord.py's class: the same constructor, ``all()``,
``none()``, ``merge()`` and ``to_dict()``, and it can be set once on the client
as ``allowed_mentions=`` to apply to every message sent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ._types import UNSET, UnsetType


class _DefaultBool:
    """Placeholder for a field left at its default, which behaves as ``True``.

    ``merge()`` only takes a field from the other object when that field was set
    explicitly, so an unset field has to be told apart from an explicit ``True``.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "True"

    def __eq__(self, other: object) -> bool:
        return other is True

    def __hash__(self) -> int:
        return hash(True)

    def __bool__(self) -> bool:
        return True


default: Any = _DefaultBool()

_Targets = bool | Sequence[Any]


def _target_id(target: Any) -> str:
    """Return the snowflake of a user, member, role, ``Object``, int or str."""
    value = getattr(target, "id", target)
    if isinstance(value, bool):
        raise TypeError("Allowed mention targets must be IDs or objects with an id")
    return str(int(value))


@dataclass(slots=True)
class AllowedMentions:
    """Which mentions in a message's text are allowed to notify.

    Set it per message with ``send(..., allowed_mentions=...)``, or once on the
    client with ``fluxer.Client(allowed_mentions=...)`` to apply to every message.
    A per-message object is merged over the client one: only the fields it sets
    explicitly replace the client's.

    Fluxer cannot combine a list of users or roles with parsed categories in one
    request. When ``users`` or ``roles`` is a list, any other category left at its
    default is turned off. Setting one explicitly to ``True`` raises ``ValueError``
    when the payload is built.

    Attributes:
        everyone: Whether ``@everyone`` and ``@here`` can notify.
        users: ``True`` for every mentioned user, ``False`` for none, or the users
            (objects with an ``id``, or IDs) allowed to be notified. At most 100.
        roles: ``True`` for every mentioned role, ``False`` for none, or the roles
            (objects with an ``id``, or IDs) allowed to be notified. At most 100.
        replied_user: Whether a reply notifies the author of the referenced message.
    """

    everyone: bool = default
    users: _Targets = default
    roles: _Targets = default
    replied_user: bool = default

    @classmethod
    def all(cls) -> AllowedMentions:
        """Allow every mention, with all fields explicitly ``True``.

        Returns:
            A policy that allows everything.
        """
        return cls(everyone=True, users=True, roles=True, replied_user=True)

    @classmethod
    def none(cls) -> AllowedMentions:
        """Allow no mention, with all fields ``False``.

        Returns:
            A policy that suppresses every notification.
        """
        return cls(everyone=False, users=False, roles=False, replied_user=False)

    def merge(self, other: AllowedMentions) -> AllowedMentions:
        """Combine two policies, preferring the fields ``other`` set explicitly.

        Args:
            other: Policy whose explicitly set fields override this one's.

        Returns:
            A new policy.
        """
        return AllowedMentions(
            everyone=self.everyone if other.everyone is default else other.everyone,
            users=self.users if other.users is default else other.users,
            roles=self.roles if other.roles is default else other.roles,
            replied_user=self.replied_user
            if other.replied_user is default
            else other.replied_user,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a Fluxer allowed mentions object.

        Returns:
            The payload, with ``replied_user`` always included.

        Raises:
            ValueError: If a list of users or roles is combined with a category
                explicitly set to ``True``, which Fluxer rejects.
        """
        lists: dict[str, list[str]] = {}
        parsed: list[str] = []
        for category, value in (
            ("everyone", self.everyone),
            ("users", self.users),
            ("roles", self.roles),
        ):
            if isinstance(value, (bool, _DefaultBool)):
                if value:
                    parsed.append(category)
            else:
                ids = [_target_id(target) for target in value]
                if ids:
                    lists[category] = ids
        if lists and parsed:
            explicit = [
                category
                for category in parsed
                if getattr(self, category) is not default
            ]
            if explicit:
                raise ValueError(
                    "Fluxer cannot combine allowed mention lists "
                    f"({', '.join(lists)}) with {', '.join(explicit)}=True; "
                    "pass a list or False for those as well"
                )
            parsed = []
        data: dict[str, Any] = {"parse": parsed, **lists}
        data["replied_user"] = bool(self.replied_user)
        return data


def _resolve_allowed_mentions(
    value: Any,
    previous: AllowedMentions | None,
    *,
    mention_author: bool | None = None,
) -> Any:
    """Build the ``allowed_mentions`` payload value for a send or edit.

    Args:
        value: The caller's policy: an ``AllowedMentions``, a raw dict sent as is,
            ``None`` (send null on an edit, nothing on a send), or ``UNSET``.
        previous: The client-wide default, or None.
        mention_author: Overrides ``replied_user`` when not None.

    Returns:
        The payload value, ``None`` for an explicit null, or ``UNSET`` to omit it.
    """
    if isinstance(value, AllowedMentions):
        result: Any = (previous.merge(value) if previous else value).to_dict()
    elif isinstance(value, UnsetType):
        result = previous.to_dict() if previous is not None else UNSET
    elif value is None:
        result = None
    else:
        result = value.to_dict() if hasattr(value, "to_dict") else value
    if mention_author is not None:
        base = result if isinstance(result, dict) else AllowedMentions().to_dict()
        result = {**base, "replied_user": mention_author}
    return result


__all__ = ("AllowedMentions",)
