"""Mixins helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations


class EqualityComparable:
    """Equality Comparable data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
    """

    id: int

    def __eq__(self, other: object) -> bool:
        """Compare this object with another value using its identity semantics.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return isinstance(other, self.__class__) and other.id == self.id


class Hashable(EqualityComparable):
    """Hashable data and behaviour.

    Attributes:
        id: Identity of the object used by this operation.
    """

    def __hash__(self) -> int:
        """Return the hash used for identity-based collection lookup.

        Returns:
            The result of this operation.
        """
        return self.id >> 22


__all__ = ("EqualityComparable", "Hashable")
