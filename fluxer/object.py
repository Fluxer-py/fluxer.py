"""Object helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from datetime import datetime

from .utils import snowflake_to_datetime


class Object:
    """Lightweight object carrying only a Fluxer snowflake ID.

    Attributes:
        id: Id.
        created_at: Return the UTC creation time encoded in this object's snowflake.
    """

    id: int

    def __init__(self, id: int | str) -> None:
        """Initialize the object with the supplied configuration.

        Args:
            id: Identity of the object used by this operation.
        """
        try:
            self.id = int(id)
        except ValueError:
            raise TypeError("id parameter must be convertible to int") from None

    @property
    def created_at(self) -> datetime:
        """Return the UTC creation time encoded in this object's snowflake.

        Returns:
            The result of this operation.
        """
        return snowflake_to_datetime(self.id)

    def __repr__(self) -> str:
        """Return a diagnostic representation of this object.

        Returns:
            The result of this operation.
        """
        return f"<Object id={self.id}>"

    def __eq__(self, other: object) -> bool:
        """Compare this object with another value using its identity semantics.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return isinstance(other, Object) and other.id == self.id

    def __hash__(self) -> int:
        """Return the hash used for identity-based collection lookup.

        Returns:
            The result of this operation.
        """
        return self.id >> 22


__all__ = ("Object",)
