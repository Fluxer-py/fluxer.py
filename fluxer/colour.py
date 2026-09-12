"""Colour helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations


class Colour:
    """Integer RGB colour helper for Fluxer payloads.

    Attributes:
        value: Stored integer value represented by this wrapper.
        r: Return the red component of this packed colour.
        g: Return the green component of this packed colour.
        b: Return the blue component of this packed colour.
    """

    value: int

    __slots__ = ("value",)

    def __init__(self, value: int = 0) -> None:
        """Initialize the colour with the supplied configuration.

        Args:
            value: Value to convert, assign, or compare.
        """
        if not 0 <= int(value) <= 0xFFFFFF:
            raise ValueError("colour value must be between 0x000000 and 0xFFFFFF")
        self.value = int(value)

    @classmethod
    def default(cls) -> "Colour":
        """Default.

        Returns:
            The result of this operation.
        """
        return cls(0)

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int) -> "Colour":
        """Build a packed colour from red, green, and blue components.

        Args:
            r: Red component from 0 through 255.
            g: Green component from 0 through 255.
            b: Blue component from 0 through 255.

        Returns:
            A parsed Colour instance.
        """
        return cls((r << 16) + (g << 8) + b)

    @classmethod
    def from_str(cls, value: str) -> "Colour":
        """Parse the supported hexadecimal or RGB colour notation.

        Args:
            value: Value to convert, assign, or compare.

        Returns:
            A parsed Colour instance.
        """
        value = value.strip()
        if value.startswith("#"):
            value = value[1:]
        elif value.lower().startswith("0x"):
            value = value[2:]
        elif value.lower().startswith("rgb(") and value.endswith(")"):
            parts = [int(part.strip()) for part in value[4:-1].split(",")]
            if len(parts) != 3:
                raise ValueError("rgb() requires three components")
            return cls.from_rgb(*parts)
        return cls(int(value, 16))

    @property
    def r(self) -> int:
        """Return the red component of this packed colour.

        Returns:
            The result of this operation.
        """
        return (self.value >> 16) & 0xFF

    @property
    def g(self) -> int:
        """Return the green component of this packed colour.

        Returns:
            The result of this operation.
        """
        return (self.value >> 8) & 0xFF

    @property
    def b(self) -> int:
        """Return the blue component of this packed colour.

        Returns:
            The result of this operation.
        """
        return self.value & 0xFF

    def to_rgb(self) -> tuple[int, int, int]:
        """Return the red, green, and blue components in that order.

        Returns:
            The result of this operation.
        """
        return self.r, self.g, self.b

    def __int__(self) -> int:
        """Return the stored integer value.

        Returns:
            The result of this operation.
        """
        return self.value

    def __str__(self) -> str:
        """Return the object's user-facing text representation.

        Returns:
            The result of this operation.
        """
        return f"#{self.value:06x}"

    def __repr__(self) -> str:
        """Return a diagnostic representation of this object.

        Returns:
            The result of this operation.
        """
        return f"<Colour value=0x{self.value:06x}>"

    def __eq__(self, other: object) -> bool:
        """Compare this object with another value using its identity semantics.

        Args:
            other: Other operand used for comparison.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return isinstance(other, Colour) and other.value == self.value


Color = Colour


__all__ = ("Colour", "Color")
