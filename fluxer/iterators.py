"""Asynchronous iteration over existing in-memory values and transformations.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")


class _AsyncIterator(AsyncIterator[T]):
    async def next(self) -> T:
        """Next.

        Returns:
            The result of this operation.
        """
        return await self.__anext__()

    async def flatten(self) -> list[T]:
        """Flatten.

        Returns:
            The result of this operation.
        """
        return [item async for item in self]

    def map(self, func: Callable[[T], U]) -> "_MappedAsyncIterator[T, U]":
        """Map.

        Args:
            func: Callable registered or applied by this helper.

        Returns:
            The result of this operation.
        """
        return _MappedAsyncIterator(self, func)

    def filter(self, predicate: Callable[[T], bool]) -> "_FilteredAsyncIterator[T]":
        """Filter.

        Args:
            predicate: Condition used to accept an item or permit execution.

        Returns:
            The result of this operation.
        """
        return _FilteredAsyncIterator(self, predicate)


class ListAsyncIterator(_AsyncIterator[T], Generic[T]):
    """List Async Iterator data and behaviour.

    Attributes:
        values: Values retained in order for iteration.
        index: Zero-based position of the next item to consume.
    """

    def __init__(self, values: list[T]) -> None:
        """Initialize the list async iterator with the supplied configuration.

        Args:
            values: Values retained in order for iteration.
        """
        self.values: list[T] = values
        self.index: int = 0

    def __aiter__(self) -> "ListAsyncIterator[T]":
        """Return this object's asynchronous iterator.

        Returns:
            This instance, allowing chained calls.
        """
        return self

    async def __anext__(self) -> T:
        """Consume the next item from the asynchronous iterator.

        Returns:
            The result of this operation.
        """
        if self.index >= len(self.values):
            raise StopAsyncIteration
        value = self.values[self.index]
        self.index += 1
        return value


class _MappedAsyncIterator(_AsyncIterator[U], Generic[T, U]):
    def __init__(self, iterator: AsyncIterator[T], func: Callable[[T], U]) -> None:
        self.iterator: AsyncIterator[T] = iterator
        self.func: Callable[[T], U] = func

    def __aiter__(self) -> "_MappedAsyncIterator[T, U]":
        return self

    async def __anext__(self) -> U:
        return self.func(await self.iterator.__anext__())


class _FilteredAsyncIterator(_AsyncIterator[T], Generic[T]):
    def __init__(
        self, iterator: AsyncIterator[T], predicate: Callable[[T], bool]
    ) -> None:
        self.iterator: AsyncIterator[T] = iterator
        self.predicate: Callable[[T], bool] = predicate

    def __aiter__(self) -> "_FilteredAsyncIterator[T]":
        return self

    async def __anext__(self) -> T:
        while True:
            value = await self.iterator.__anext__()
            if self.predicate(value):
                return value


__all__ = ("ListAsyncIterator",)
