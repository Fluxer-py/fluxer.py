"""Init helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any


class Loop:
    """Loop data and behaviour.

    Attributes:
        coro: Coroutine function invoked by the task or command wrapper.
        reconnect: Whether the task loop retries handled transient failures.
        count: Number of task iterations; None continues until stopped.
        current_loop: Return the number of completed task iterations.
        seconds: Seconds contributing to the task interval or timeout.
        minutes: Minutes contributing to the task interval.
        hours: Hours contributing to the task interval.
    """

    def __init__(
        self,
        coro: Callable[..., Awaitable[Any]],
        seconds: float,
        hours: float,
        minutes: float,
        count: int | None,
        reconnect: bool,
        loop: Any = None,
    ) -> None:
        """Initialize the loop with the supplied configuration.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.
            seconds: Seconds contributing to the task interval or timeout.
            hours: Hours contributing to the task interval.
            minutes: Minutes contributing to the task interval.
            count: Number of task iterations; None continues until stopped.
            reconnect: Whether the task loop retries handled transient failures.
            loop: Loop used by this operation.
        """
        if not inspect.iscoroutinefunction(coro):
            raise TypeError("Expected a coroutine function")
        self.coro: Callable[..., Awaitable[Any]] = coro
        self.reconnect: bool = reconnect
        self.count: int | None = count
        self._task: asyncio.Task[Any] | None = None
        self._before_loop: Callable[..., Awaitable[Any]] | None = None
        self._after_loop: Callable[..., Awaitable[Any]] | None = None
        self._error: Callable[[Exception], Awaitable[Any]] | None = None
        self._current_loop = 0
        self._has_failed = False
        self._injected: Any | None = None
        self.change_interval(seconds=seconds, minutes=minutes, hours=hours)

    def __get__(self, obj: Any, objtype: type[Any]) -> "Loop":
        """Bind this descriptor to the supplied instance.

        Args:
            obj: Obj used by this operation.
            objtype: Objtype used by this operation.

        Returns:
            The result of this operation.
        """
        if obj is None:
            return self
        copy = type(self)(
            self.coro,
            self.seconds,
            self.hours,
            self.minutes,
            self.count,
            self.reconnect,
        )
        copy._before_loop = self._before_loop
        copy._after_loop = self._after_loop
        copy._error = self._error
        copy._injected = obj
        return copy

    @property
    def current_loop(self) -> int:
        """Return the number of completed task iterations.

        Returns:
            The result of this operation.
        """
        return self._current_loop

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Invoke the wrapped callback with the supplied arguments.

        Args:
            *args: Positional arguments forwarded to the wrapped callback.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        injected = getattr(self, "_injected", None)
        if injected is not None:
            return await self.coro(injected, *args, **kwargs)
        return await self.coro(*args, **kwargs)

    async def _call_hook(self, hook: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        injected = getattr(self, "_injected", None)
        if injected is not None:
            return await hook(injected, *args)
        return await hook(*args)

    async def _loop(self, *args: Any, **kwargs: Any) -> None:
        try:
            if self._before_loop:
                await self._call_hook(self._before_loop)
            while self.count is None or self._current_loop < self.count:
                try:
                    await self(*args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._has_failed = True
                    if self._error:
                        await self._call_hook(self._error, exc)
                    if not self.reconnect:
                        raise
                self._current_loop += 1
                await asyncio.sleep(
                    self.seconds + self.minutes * 60 + self.hours * 3600
                )
        finally:
            if self._after_loop:
                await self._call_hook(self._after_loop)

    def start(self, *args: Any, **kwargs: Any) -> asyncio.Task[Any]:
        """Start.

        Args:
            *args: Positional arguments forwarded to the wrapped callback.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        if self._task and not self._task.done():
            raise RuntimeError("Task is already launched")
        self._task = asyncio.create_task(self._loop(*args, **kwargs))
        return self._task

    def stop(self) -> None:
        """Stop.

        Returns:
            None.
        """
        self.cancel()

    def cancel(self) -> None:
        """Cancel.

        Returns:
            None.
        """
        if self._task:
            self._task.cancel()

    def restart(self, *args: Any, **kwargs: Any) -> None:
        """Restart.

        Args:
            *args: Positional arguments forwarded to the wrapped callback.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            None.
        """
        self.cancel()
        self.start(*args, **kwargs)

    def get_task(self) -> asyncio.Task[Any] | None:
        """Return the asyncio task currently running this loop, if any.

        Returns:
            The requested task, or None when no matching value is available.
        """
        return self._task

    def is_running(self) -> bool:
        """Return whether the loop's asyncio task is still active.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self._task is not None and not self._task.done()

    def failed(self) -> bool:
        """Return whether the task loop stopped because of an unhandled failure.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self._has_failed

    def before_loop(
        self, coro: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        """Register the coroutine run before task iterations begin.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self._before_loop = coro
        return coro

    def after_loop(
        self, coro: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        """Register the coroutine run when the task loop exits.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self._after_loop = coro
        return coro

    def error(
        self, coro: Callable[[Exception], Awaitable[Any]]
    ) -> Callable[[Exception], Awaitable[Any]]:
        """Error.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self._error = coro
        return coro

    def change_interval(
        self, *, seconds: float = 0, minutes: float = 0, hours: float = 0
    ) -> None:
        """Update the interval used between task-loop iterations.

        Args:
            seconds: Seconds contributing to the task interval or timeout.
            minutes: Minutes contributing to the task interval.
            hours: Hours contributing to the task interval.

        Returns:
            None.
        """
        self.seconds: float = seconds
        self.minutes: float = minutes
        self.hours: float = hours


def loop(
    *,
    seconds: float = 0,
    minutes: float = 0,
    hours: float = 0,
    count: int | None = None,
    reconnect: bool = True,
    loop: Any = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Loop]:
    """Wrap an async function in the existing interval task loop.

    Args:
        seconds: Seconds contributing to the task interval or timeout.
        minutes: Minutes contributing to the task interval.
        hours: Hours contributing to the task interval.
        count: Number of task iterations; None continues until stopped.
        reconnect: Whether the task loop retries handled transient failures.
        loop: Loop used by this operation.

    Returns:
        The configured decorator or callback wrapper.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Loop:
        return Loop(func, seconds, hours, minutes, count, reconnect, loop)

    return decorator


__all__ = ("Loop", "loop")
