from __future__ import annotations

import inspect
from typing import Any, Callable, cast

from .core import Command, command


class CogMeta(type):
    def __new__(
        mcls, name: str, bases: tuple[type, ...], attrs: dict[str, Any], **kwargs: Any
    ) -> "CogMeta":
        commands: list[Command] = []
        listeners: list[tuple[str, str]] = []
        cls = super().__new__(mcls, name, bases, attrs)
        for base in reversed(cls.__mro__):
            for attr_name, value in base.__dict__.items():
                if isinstance(value, Command):
                    if value.parent is None:
                        commands.append(value)
                listener_name = getattr(value, "__cog_listener_name__", None)
                if listener_name:
                    listeners.append((listener_name, attr_name))
        cls.__cog_commands__ = commands  # type: ignore[attr-defined]
        cls.__cog_listeners__ = listeners  # type: ignore[attr-defined]
        return cls


class Cog(metaclass=CogMeta):
    __cog_commands__: list[Command]
    __cog_listeners__: list[tuple[str, str]]

    def __init__(self, bot: Any | None = None) -> None:
        self.bot = bot

    command = staticmethod(command)

    @classmethod
    def listener(cls, name: str | None = None) -> Callable[[Any], Any]:
        def decorator(func: Any) -> Any:
            setattr(func, "__cog_listener_name__", name or func.__name__)
            return func

        return decorator

    @property
    def qualified_name(self) -> str:
        return self.__class__.__name__

    @property
    def description(self) -> str:
        return inspect.getdoc(self.__class__) or ""

    def get_commands(self) -> list[Command]:
        return list(self.__cog_commands__)

    def walk_commands(self) -> list[Command]:
        out: list[Command] = []
        for cmd in self.get_commands():
            out.append(cmd)
            if hasattr(cmd, "walk_commands"):
                out.extend(cast(Any, cmd).walk_commands())
        return out

    def get_listeners(self) -> list[tuple[str, Any]]:
        return [
            (name, getattr(self, method_name))
            for name, method_name in self.__cog_listeners__
        ]

    async def cog_load(self) -> None:
        pass

    async def cog_unload(self) -> None:
        pass

    async def cog_command_error(self, ctx: Any, error: Exception) -> None:
        raise error

    async def cog_before_invoke(self, ctx: Any) -> None:
        pass

    async def cog_after_invoke(self, ctx: Any) -> None:
        pass
