from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AuditLogEntry:
    id: int
    action_type: str | int | None = None
    user_id: int | None = None
    target_id: int | None = None
    changes: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "AuditLogEntry":
        return cls(
            id=int(data["id"]),
            action_type=data.get("action_type") or data.get("action"),
            user_id=int(data["user_id"]) if data.get("user_id") else None,
            target_id=int(data["target_id"]) if data.get("target_id") else None,
            changes=data.get("changes", []),
            raw_data=data,
        )


@dataclass(slots=True)
class AuditLog:
    entries: list[AuditLogEntry]
    users: list[dict[str, Any]] = field(default_factory=list)
    webhooks: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "AuditLog":
        entries = data.get("audit_log_entries") or data.get("entries") or []
        return cls(
            entries=[AuditLogEntry.from_data(entry) for entry in entries],
            users=data.get("users", []),
            webhooks=data.get("webhooks", []),
            raw_data=data,
        )


AuditLogDiff = dict[str, Any]
AuditLogChanges = list[dict[str, Any]]
