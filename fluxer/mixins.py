from __future__ import annotations


class EqualityComparable:
    id: int

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and other.id == self.id


class Hashable(EqualityComparable):
    def __hash__(self) -> int:
        return self.id >> 22
