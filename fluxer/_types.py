"""Internal payload primitives shared by existing Fluxer operations.

The unset value distinguishes an omitted update from an explicit JSON null.
These helpers are implementation details, not additional resource APIs.
"""

from __future__ import annotations

from typing import Any, TypedDict

__all__: tuple[str, ...] = ()


class UnsetType:
    """Represent an omitted field using one stateless, false-valued sentinel.

    Note:
        This internal type carries no mutable state.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        """Return a diagnostic representation of this object.

        Returns:
            The result of this operation.
        """
        return "UNSET"

    def __bool__(self) -> bool:
        """Return the truth value of the current object state.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return False


UNSET = UnsetType()


class PinPage(TypedDict):
    """Describe a single timestamp-paginated response from the pins route.

    Attributes:
        items: Pin entries containing message and pinned_at metadata.
        has_more: Has more used by this operation.
    """

    items: list[dict[str, Any]]
    has_more: bool


class UploadFile(TypedDict):
    """Hold repeatable bytes for an existing direct multipart upload.

    Attributes:
        filename: Filename presented to the server and recipients.
        data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
    """

    filename: str
    data: bytes


def optional_id(value: Any) -> int | None:
    """Decode a nullable identifier without treating zero as absence.

    Args:
        value: Value to convert, assign, or compare.

    Returns:
        The result of this operation.
    """
    return None if value is None else int(value)
