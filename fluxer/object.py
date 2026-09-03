from __future__ import annotations

from datetime import datetime

from .utils import snowflake_to_datetime


class Object:
    """Lightweight object carrying only a Fluxer snowflake ID."""

    def __init__(self, id: int | str) -> None:
        try:
            self.id = int(id)
        except ValueError:
            raise TypeError("id parameter must be convertible to int") from None

    @property
    def created_at(self) -> datetime:
        return snowflake_to_datetime(self.id)

    def __repr__(self) -> str:
        return f"<Object id={self.id}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Object) and other.id == self.id

    def __hash__(self) -> int:
        return self.id >> 22
