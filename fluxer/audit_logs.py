"""Audit logs helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .models.user import User

if TYPE_CHECKING:
    from .http import HTTPClient


def _int(value: Any) -> int | None:
    """Convert a snowflake or numeric string, keeping None and non-numeric values out."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class AuditLogChange:
    """One field an audited action changed, with its value on each side.

    ``old_value`` and ``new_value`` are deliberately untyped: their shape
    depends on ``key`` (see "Change fields" in Fluxer's guild audit log
    documentation), and they are passed through exactly as Fluxer sent them.
    A value is one of:

    - ``str``: text, and every snowflake or permission mask, which Fluxer
      sends as a decimal string (``"1234567890"``), never as an int.
    - ``int`` or ``float``: bounded numbers such as positions or colours.
    - ``bool``.
    - ``None``: the field was explicitly null on that side.
    - ``list[str]`` or ``list[int]``: for example a member's ``roles``.
    - ``dict`` with ``"added"`` and ``"removed"`` lists of strings: only for
      the ``permissions_diff`` key of a role update, which has ``new_value``
      alone.

    A creation has only ``new_value``, a deletion only ``old_value``, and a
    modification both. A side that was absent is also None here, so use
    :attr:`has_old_value` / :attr:`has_new_value` to tell "absent" from
    "explicitly null". An update lists only fields whose value differs.

    Attributes:
        key: Name of the changed field, from the change fields of the target entity.
        old_value: Value before the action; None when absent or null.
        new_value: Value after the action; None when absent or null.
        raw_data: Original change object; excluded from repr.
        has_old_value: Whether the payload included ``old_value``.
        has_new_value: Whether the payload included ``new_value``.
    """

    key: str
    old_value: Any = None
    new_value: Any = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def has_old_value(self) -> bool:
        """Whether the payload included ``old_value`` (possibly as null).

        Returns:
            False for a creation, which records only the new value.
        """
        return "old_value" in self.raw_data

    @property
    def has_new_value(self) -> bool:
        """Whether the payload included ``new_value`` (possibly as null).

        Returns:
            False for a deletion, which records only the old value.
        """
        return "new_value" in self.raw_data

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> AuditLogChange:
        """Build an AuditLogChange from its decoded payload.

        Args:
            data: Audit log change object.

        Returns:
            The parsed change, with values passed through unchanged.
        """
        return cls(
            key=data.get("key", ""),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            raw_data=dict(data),
        )


@dataclass(slots=True)
class AuditLogOptions:
    """Action-specific details of an audit log entry; unused fields are None.

    Attributes:
        channel_id: Channel the action happened in.
        count: Number of entities affected.
        delete_member_days: Days of inactivity used by a member prune.
        delete_message_seconds: Seconds of messages deleted with a ban.
        id: ID of the overwritten entity.
        integration_type: Integration type.
        message_id: Message the action targeted.
        members_removed: Number of members removed by a prune.
        role_name: Name of the role in a permission overwrite.
        type: Type of the overwritten entity.
        inviter_id: Account that created the invite.
        max_age: Invite lifetime in seconds.
        max_uses: Invite use limit.
        temporary: Whether the invite grants temporary membership.
        uses: Invite use count.
        raw_data: Original payload; excluded from repr.
    """

    channel_id: int | None = None
    count: int | None = None
    delete_member_days: int | None = None
    delete_message_seconds: int | None = None
    id: int | None = None
    integration_type: int | None = None
    message_id: int | None = None
    members_removed: int | None = None
    role_name: str | None = None
    type: int | None = None
    inviter_id: int | None = None
    max_age: int | None = None
    max_uses: int | None = None
    temporary: bool | None = None
    uses: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> AuditLogOptions:
        """Build AuditLogOptions from its decoded payload.

        Args:
            data: Audit log options object.

        Returns:
            The parsed options.
        """
        return cls(
            channel_id=_int(data.get("channel_id")),
            count=_int(data.get("count")),
            delete_member_days=_int(data.get("delete_member_days")),
            delete_message_seconds=_int(data.get("delete_message_seconds")),
            id=_int(data.get("id")),
            integration_type=_int(data.get("integration_type")),
            message_id=_int(data.get("message_id")),
            members_removed=_int(data.get("members_removed")),
            role_name=data.get("role_name"),
            type=_int(data.get("type")),
            inviter_id=_int(data.get("inviter_id")),
            max_age=_int(data.get("max_age")),
            max_uses=_int(data.get("max_uses")),
            temporary=data.get("temporary"),
            uses=_int(data.get("uses")),
            raw_data=dict(data),
        )


@dataclass(slots=True)
class AuditLogWebhook:
    """A webhook referenced by audit log entries.

    Attributes:
        id: Webhook ID.
        type: Webhook type.
        guild_id: Guild the webhook belongs to, or None.
        channel_id: Channel the webhook posts to, or None.
        name: Webhook name.
        avatar_hash: Avatar image hash, or None.
    """

    id: int
    type: int = 0
    guild_id: int | None = None
    channel_id: int | None = None
    name: str = ""
    avatar_hash: str | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> AuditLogWebhook:
        """Build an AuditLogWebhook from its decoded payload.

        Args:
            data: Audit log webhook object.

        Returns:
            The parsed webhook.
        """
        return cls(
            id=int(data["id"]),
            type=data.get("type", 0),
            guild_id=_int(data.get("guild_id")),
            channel_id=_int(data.get("channel_id")),
            name=data.get("name", ""),
            avatar_hash=data.get("avatar_hash", data.get("avatar")),
        )


@dataclass(slots=True)
class AuditLogEntry:
    """Audit Log Entry data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
        action_type: Action type used by this operation.
        user_id: Identity of the user used by this operation.
        target_id: Identity of the target used by this operation.
        reason: Audit-log reason forwarded when the underlying operation supports it.
        options: Action-specific details, when the action records any.
        changes: Properties the action changed.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: int
    action_type: int | None = None
    user_id: int | None = None
    target_id: str | None = None
    reason: str | None = None
    options: AuditLogOptions | None = None
    changes: list[AuditLogChange] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "AuditLogEntry":
        """Build a AuditLogEntry from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed AuditLogEntry instance.
        """
        return cls(
            id=int(data["id"]),
            action_type=int(data["action_type"])
            if data.get("action_type") is not None
            else None,
            user_id=int(data["user_id"]) if data.get("user_id") else None,
            target_id=str(data["target_id"])
            if data.get("target_id") is not None
            else None,
            reason=data.get("reason"),
            options=AuditLogOptions.from_data(data["options"])
            if isinstance(data.get("options"), dict)
            else None,
            changes=[
                AuditLogChange.from_data(item) for item in data.get("changes", [])
            ],
            raw_data=data,
        )


@dataclass(slots=True)
class AuditLog:
    """Audit Log data and behaviour.

    Attributes:
        entries: Entries used by this operation.
        users: Accounts referenced by the entries.
        webhooks: Webhooks referenced by the entries.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    entries: list[AuditLogEntry]
    users: list[User] = field(default_factory=list)
    webhooks: list[AuditLogWebhook] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> "AuditLog":
        """Build a AuditLog from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind to the referenced users.

        Returns:
            A parsed AuditLog instance.
        """
        entries = data.get("audit_log_entries") or data.get("entries") or []
        return cls(
            entries=[AuditLogEntry.from_data(entry) for entry in entries],
            users=[User.from_data(item, http) for item in data.get("users", [])],
            webhooks=[
                AuditLogWebhook.from_data(item) for item in data.get("webhooks", [])
            ],
            raw_data=data,
        )


AuditLogDiff = AuditLogChange
AuditLogChanges = list[AuditLogChange]


__all__ = (
    "AuditLogEntry",
    "AuditLog",
    "AuditLogChange",
    "AuditLogOptions",
    "AuditLogWebhook",
    "AuditLogDiff",
    "AuditLogChanges",
)
