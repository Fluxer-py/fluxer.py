from __future__ import annotations


class Colour:
    """Integer RGB colour helper for Fluxer payloads."""

    __slots__ = ("value",)

    def __init__(self, value: int = 0) -> None:
        if not 0 <= int(value) <= 0xFFFFFF:
            raise ValueError("colour value must be between 0x000000 and 0xFFFFFF")
        self.value = int(value)

    @classmethod
    def default(cls) -> "Colour":
        return cls(0)

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int) -> "Colour":
        return cls((r << 16) + (g << 8) + b)

    @classmethod
    def from_str(cls, value: str) -> "Colour":
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
        return (self.value >> 16) & 0xFF

    @property
    def g(self) -> int:
        return (self.value >> 8) & 0xFF

    @property
    def b(self) -> int:
        return self.value & 0xFF

    def to_rgb(self) -> tuple[int, int, int]:
        return self.r, self.g, self.b

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return f"#{self.value:06x}"

    def __repr__(self) -> str:
        return f"<Colour value=0x{self.value:06x}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Colour) and other.value == self.value


Color = Colour
