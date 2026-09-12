"""Audit logs helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AuditLogEntry:
    """Audit Log Entry data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
        action_type: Action type used by this operation.
        user_id: Identity of the user used by this operation.
        target_id: Identity of the target used by this operation.
        reason: Audit-log reason forwarded when the underlying operation supports it.
        options: Action-specific audit metadata supplied by the server.
        changes: Changes used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    id: int
    action_type: int | None = None
    user_id: int | None = None
    target_id: str | None = None
    reason: str | None = None
    options: dict[str, Any] | None = None
    changes: list[dict[str, Any]] = field(default_factory=list)
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
            options=data.get("options"),
            changes=data.get("changes", []),
            raw_data=data,
        )


@dataclass(slots=True)
class AuditLog:
    """Audit Log data and behaviour.

    Attributes:
        entries: Entries used by this operation.
        users: Users used by this operation.
        webhooks: Webhooks used by this operation.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    entries: list[AuditLogEntry]
    users: list[dict[str, Any]] = field(default_factory=list)
    webhooks: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "AuditLog":
        """Build a AuditLog from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.

        Returns:
            A parsed AuditLog instance.
        """
        entries = data.get("audit_log_entries") or data.get("entries") or []
        return cls(
            entries=[AuditLogEntry.from_data(entry) for entry in entries],
            users=data.get("users", []),
            webhooks=data.get("webhooks", []),
            raw_data=data,
        )


AuditLogDiff = dict[str, Any]
AuditLogChanges = list[dict[str, Any]]


__all__ = ("AuditLogEntry", "AuditLog", "AuditLogDiff", "AuditLogChanges")
