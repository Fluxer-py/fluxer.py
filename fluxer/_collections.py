"""Internal read-only entity views and weak-reference support."""

from collections.abc import Iterable, Iterator, Sequence
from typing import Generic, Protocol, TypeVar, overload


class _Identified(Protocol):
    @property
    def id(self) -> int: ...


T = TypeVar("T", bound=_Identified)


class _EntitySequence(Sequence[T], Generic[T]):
    __slots__ = ("_data",)

    def __init__(self, items: Iterable[T] = ()) -> None:
        self._data: dict[int, T] = {item.id: item for item in items}

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[T]: ...

    def __getitem__(self, index: int | slice) -> T | Sequence[T]:
        return tuple(self._data.values())[index]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[T]:
        return iter(self._data.values())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Sequence):
            return list(self) == list(other)
        return NotImplemented

    def __repr__(self) -> str:
        return repr(tuple(self))


class _WeakRefable:
    __slots__ = ("__weakref__",)
