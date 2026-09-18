"""Permission masks and guild-channel overwrite types for fluxer.py."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import enum
from typing import Any, TypedDict

from .enums import Permissions


MAX_OVERWRITE_MASK = (1 << 63) - 1
_KNOWN_PERMISSION_MASK = 0
for _permission in Permissions:
    _KNOWN_PERMISSION_MASK |= int(_permission)


class PermissionOverwriteType(enum.IntEnum):
    """Identify the kind of guild-channel overwrite target.

    Attributes:
        ROLE: An overwrite targeting a guild role.
        MEMBER: An overwrite targeting one guild member.
    """

    ROLE = 0
    MEMBER = 1


class PermissionOverwritePayload(TypedDict):
    """Describe the raw overwrite shape stored on a guild channel.

    Attributes:
        id: Decimal target snowflake.
        type: Integer overwrite target type.
        allow: Decimal string containing explicitly allowed permission bits.
        deny: Decimal string containing explicitly denied permission bits.
    """

    id: str
    type: int
    allow: str
    deny: str


def _permission_name(name: str) -> str:
    member = Permissions.__members__.get(name.upper())
    if member is None:
        raise ValueError(f"Unknown permission: {name}")
    canonical = member.name
    if canonical is None:
        raise RuntimeError("Fluxer permission is missing its canonical name")
    return canonical.lower()


def _validate_overwrite_value(value: object) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise TypeError("Permission overwrite values must be bool or None")
    return value


def _coerce_mask(value: object, *, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer permission mask")
    if isinstance(value, str):
        if not value.isdecimal():
            raise ValueError(f"{name} must be an unsigned decimal integer")
        mask = int(value)
    elif isinstance(value, int):
        mask = int(value)
    else:
        raise TypeError(f"{name} must be an integer permission mask")
    if not 0 <= mask <= MAX_OVERWRITE_MASK:
        raise ValueError(f"{name} must be between 0 and {MAX_OVERWRITE_MASK}")
    return mask


class PermissionOverwrite:
    """Build explicit allow and deny values for a guild channel.

    A permission value of ``True`` allows the operation, ``False`` denies it,
    and ``None`` leaves it unset. Permission names are lowercase attributes and
    keyword arguments. Aliases resolve to their canonical permission name.

    Attributes:
        send_messages: One example of the dynamic tri-state permission attributes.
    """

    __slots__ = ("_values",)

    def __init__(self, **permissions: bool | None) -> None:
        """Initialize an overwrite from permission keyword values.

        Args:
            **permissions: Lowercase permission names mapped to tri-state values.
        """
        object.__setattr__(self, "_values", {})
        self.update(**permissions)

    def __getattr__(self, name: str) -> bool | None:
        """Return the tri-state value for a permission attribute.

        Args:
            name: Lowercase permission name or alias.

        Returns:
            The explicit value, or ``None`` when the permission is unset.

        Raises:
            AttributeError: The name does not identify a Fluxer permission.
        """
        try:
            canonical = _permission_name(name)
        except ValueError as exc:
            raise AttributeError(name) from exc
        return self._values.get(canonical)

    def __setattr__(self, name: str, value: bool | None) -> None:
        """Set or clear a permission through its lowercase attribute.

        Args:
            name: Lowercase permission name or alias.
            value: ``True``, ``False``, or ``None``.

        Raises:
            AttributeError: The name does not identify a Fluxer permission.
            TypeError: The value is not a valid tri-state value.
        """
        if name == "_values":
            object.__setattr__(self, name, value)
            return
        try:
            canonical = _permission_name(name)
        except ValueError as exc:
            raise AttributeError(name) from exc
        checked = _validate_overwrite_value(value)
        if checked is None:
            self._values.pop(canonical, None)
        else:
            self._values[canonical] = checked

    def __iter__(self) -> Iterator[tuple[str, bool | None]]:
        """Iterate over canonical permission names and tri-state values.

        Yields:
            Each canonical lowercase permission name and its current value.
        """
        for permission in Permissions:
            canonical = permission.name
            if canonical is None:
                continue
            name = canonical.lower()
            yield name, self._values.get(name)

    def __eq__(self, other: object) -> bool:
        """Compare two overwrites by their explicit permission values.

        Args:
            other: Object to compare with this overwrite.

        Returns:
            Whether both overwrites contain the same explicit values.
        """
        if not isinstance(other, PermissionOverwrite):
            return NotImplemented
        return self._values == other._values

    def __repr__(self) -> str:
        """Return a diagnostic representation of the overwrite.

        Returns:
            A representation containing only explicit permission values.
        """
        values = ", ".join(f"{key}={value!r}" for key, value in self._values.items())
        return f"PermissionOverwrite({values})"

    def update(self, **permissions: bool | None) -> None:
        """Apply one or more tri-state permission values.

        Args:
            **permissions: Lowercase permission names mapped to tri-state values.

        Raises:
            ValueError: A name does not identify a Fluxer permission.
            TypeError: A value is not ``True``, ``False``, or ``None``.
        """
        validated: list[tuple[str, bool | None]] = []
        for name, value in permissions.items():
            validated.append((_permission_name(name), _validate_overwrite_value(value)))
        for name, value in validated:
            if value is None:
                self._values.pop(name, None)
            else:
                self._values[name] = value

    def pair(self) -> tuple[Permissions, Permissions]:
        """Return separate allow and deny permission masks.

        Returns:
            The explicit allow mask followed by the explicit deny mask.
        """
        allow = Permissions(0)
        deny = Permissions(0)
        for name, value in self._values.items():
            permission = Permissions.__members__[name.upper()]
            if value is True:
                allow |= permission
            elif value is False:
                deny |= permission
        return allow, deny

    @classmethod
    def from_pair(
        cls,
        allow: int | str | Permissions,
        deny: int | str | Permissions,
    ) -> PermissionOverwrite:
        """Build an overwrite from separate allow and deny masks.

        Undefined bits are discarded. When a bit occurs in both masks, the
        allow value takes precedence.

        Args:
            allow: Explicitly allowed permission mask.
            deny: Explicitly denied permission mask.

        Returns:
            A tri-state overwrite representing the known permission bits.
        """
        allow_mask = _coerce_mask(allow, name="allow") & _KNOWN_PERMISSION_MASK
        deny_mask = _coerce_mask(deny, name="deny") & _KNOWN_PERMISSION_MASK
        overwrite = cls()
        for permission in Permissions:
            if allow_mask & permission:
                overwrite._values[permission.name.lower()] = True
            elif deny_mask & permission:
                overwrite._values[permission.name.lower()] = False
        return overwrite

    def is_empty(self) -> bool:
        """Return whether no permission has an explicit value.

        Returns:
            ``True`` when every permission is unset.
        """
        return not self._values


@dataclass(frozen=True, slots=True)
class ChannelPermissionOverwrite:
    """Represent one stored guild-channel permission overwrite.

    Attributes:
        id: Snowflake of the targeted role or member.
        type: Kind of target selected by the overwrite.
        allow: Explicitly allowed permission mask.
        deny: Explicitly denied permission mask.
    """

    id: int
    type: PermissionOverwriteType
    allow: Permissions
    deny: Permissions

    def __post_init__(self) -> None:
        """Normalize values supplied to the immutable record.

        Raises:
            TypeError: The ID or either mask has an unsupported type.
            ValueError: The target type or either mask is outside its valid range.
        """
        if isinstance(self.id, bool):
            raise TypeError("Overwrite id must be an integer snowflake")
        if self.id <= 0:
            raise ValueError("Overwrite id must be a positive integer snowflake")
        if isinstance(self.type, bool):
            raise TypeError("Overwrite type must be ROLE or MEMBER")
        object.__setattr__(self, "id", int(self.id))
        object.__setattr__(self, "type", PermissionOverwriteType(self.type))
        object.__setattr__(
            self, "allow", Permissions(_coerce_mask(self.allow, name="allow"))
        )
        object.__setattr__(
            self, "deny", Permissions(_coerce_mask(self.deny, name="deny"))
        )

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> ChannelPermissionOverwrite:
        """Parse a stored overwrite payload.

        Args:
            data: Raw guild-channel overwrite payload.

        Returns:
            A validated immutable overwrite record.
        """
        raw_id = data["id"]
        if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
            raise TypeError("Overwrite id must be an integer snowflake")
        if isinstance(raw_id, str) and not raw_id.isdecimal():
            raise ValueError("Overwrite id must be an unsigned decimal integer")
        raw_type = data["type"]
        if isinstance(raw_type, bool) or not isinstance(raw_type, (int, str)):
            raise TypeError("Overwrite type must be an integer")
        if isinstance(raw_type, str) and not raw_type.isdecimal():
            raise ValueError("Overwrite type must be an unsigned decimal integer")
        allow_value = data.get("allow")
        deny_value = data.get("deny")
        return cls(
            id=int(raw_id),
            type=PermissionOverwriteType(int(raw_type)),
            allow=Permissions(
                _coerce_mask(0 if allow_value is None else allow_value, name="allow")
            ),
            deny=Permissions(
                _coerce_mask(0 if deny_value is None else deny_value, name="deny")
            ),
        )

    def to_overwrite(self) -> PermissionOverwrite:
        """Convert this record to a mutable tri-state overwrite.

        Returns:
            A permission overwrite containing all known explicit bits.
        """
        return PermissionOverwrite.from_pair(self.allow, self.deny)

    def to_dict(self) -> PermissionOverwritePayload:
        """Serialize this record to Fluxer's decimal-string payload shape.

        Returns:
            A raw overwrite dictionary suitable for channel payloads.
        """
        return {
            "id": str(self.id),
            "type": int(self.type),
            "allow": str(int(self.allow)),
            "deny": str(int(self.deny)),
        }


def parse_permission_overwrite(
    data: Mapping[str, object],
) -> PermissionOverwritePayload:
    """Normalize one raw guild-channel overwrite payload.

    Args:
        data: Raw guild-channel overwrite payload.

    Returns:
        A compatibility dictionary with normalized wire values.
    """
    return ChannelPermissionOverwrite.from_data(data).to_dict()


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
            if int(item["id"]) == guild_id
            and int(item["type"]) == PermissionOverwriteType.ROLE
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
            int(item["type"]) == PermissionOverwriteType.ROLE
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
            if int(item["type"]) == PermissionOverwriteType.MEMBER
            and int(item["id"]) == user_id
        ),
        None,
    )
    if individual is not None:
        mask = (mask & ~int(individual.get("deny") or 0)) | int(
            individual.get("allow") or 0
        )
    return Permissions(mask)


__all__ = (
    "ChannelPermissionOverwrite",
    "PermissionOverwrite",
    "PermissionOverwritePayload",
    "PermissionOverwriteType",
    "Permissions",
)
