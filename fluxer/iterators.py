from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")


class _AsyncIterator(AsyncIterator[T]):
    async def next(self) -> T:
        return await self.__anext__()

    async def flatten(self) -> list[T]:
        return [item async for item in self]

    def map(self, func: Callable[[T], U]) -> "_MappedAsyncIterator[T, U]":
        return _MappedAsyncIterator(self, func)

    def filter(self, predicate: Callable[[T], bool]) -> "_FilteredAsyncIterator[T]":
        return _FilteredAsyncIterator(self, predicate)


class ListAsyncIterator(_AsyncIterator[T], Generic[T]):
    def __init__(self, values: list[T]) -> None:
        self.values = values
        self.index = 0

    def __aiter__(self) -> "ListAsyncIterator[T]":
        return self

    async def __anext__(self) -> T:
        if self.index >= len(self.values):
            raise StopAsyncIteration
        value = self.values[self.index]
        self.index += 1
        return value


class _MappedAsyncIterator(_AsyncIterator[U], Generic[T, U]):
    def __init__(self, iterator: AsyncIterator[T], func: Callable[[T], U]) -> None:
        self.iterator = iterator
        self.func = func

    def __aiter__(self) -> "_MappedAsyncIterator[T, U]":
        return self

    async def __anext__(self) -> U:
        return self.func(await self.iterator.__anext__())


class _FilteredAsyncIterator(_AsyncIterator[T], Generic[T]):
    def __init__(
        self, iterator: AsyncIterator[T], predicate: Callable[[T], bool]
    ) -> None:
        self.iterator = iterator
        self.predicate = predicate

    def __aiter__(self) -> "_FilteredAsyncIterator[T]":
        return self

    async def __anext__(self) -> T:
        while True:
            value = await self.iterator.__anext__()
            if self.predicate(value):
                return value
