"""Cog helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, cast

from .core import Command, command


class CogMeta(type):
    """Metaclass collecting existing cog commands and event listeners.

    Attributes:
        __cog_commands__: Commands collected from the class and its bases.
        __cog_listeners__: Event names and method names collected from the class hierarchy.
        __cog_settings__: The ``command_attrs`` given in the class statement, applied
            to every command of the cog that does not set them itself.
    """

    def __new__(
        mcls: type[CogMeta],
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
        **kwargs: Any,
    ) -> "CogMeta":
        """Construct the class while collecting its declared commands and listeners.

        Args:
            name: Name to assign or resolve in this operation.
            bases: Bases used by this operation.
            attrs: Attrs used by this operation.
            **kwargs: Class keywords; ``command_attrs`` is a dict of command
                attributes, such as ``hidden=True``, applied to every command of the
                cog that does not set them itself.
        """
        settings = dict(kwargs.pop("command_attrs", {}))
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
        cls.__cog_settings__ = settings  # type: ignore[attr-defined]
        return cls


class Cog(metaclass=CogMeta):
    """Cog data and behaviour.

    Attributes:
        bot: Client owning this command, cog, or context.
        qualified_name: Return the name including the owning command groups.
        description: Description.
    """

    __cog_commands__: list[Command]
    __cog_listeners__: list[tuple[str, str]]

    def __init__(self, bot: Any | None = None) -> None:
        """Initialize the cog with the supplied configuration.

        Args:
            bot: Client owning this command, cog, or context.
        """
        self.bot: Any | None = bot

    command = staticmethod(command)

    @classmethod
    def listener(cls, name: str | None = None) -> Callable[[Any], Any]:
        """Mark a cog method as an event listener.

        Args:
            name: Name to assign or resolve in this operation.

        Returns:
            The configured decorator or callback wrapper.
        """

        def decorator(func: Any) -> Any:
            setattr(func, "__cog_listener_name__", name or func.__name__)
            return func

        return decorator

    @property
    def qualified_name(self) -> str:
        """Return the name including the owning command groups.

        Returns:
            The result of this operation.
        """
        return self.__class__.__name__

    @property
    def description(self) -> str:
        """The cog's own docstring, shown by the help command.

        Returns:
            The cleaned docstring, or an empty string when the cog class has none.
            A parent class's docstring is not inherited.
        """
        own = type(self).__dict__.get("__doc__")
        return inspect.cleandoc(own) if isinstance(own, str) else ""

    def get_commands(self) -> list[Command]:
        """Get commands.

        Returns:
            The requested commands.
        """
        return list(self.__cog_commands__)

    def walk_commands(self) -> list[Command]:
        """Walk commands.

        Returns:
            The result of this operation.
        """
        out: list[Command] = []
        for cmd in self.get_commands():
            out.append(cmd)
            if hasattr(cmd, "walk_commands"):
                out.extend(cast(Any, cmd).walk_commands())
        return out

    def get_listeners(self) -> list[tuple[str, Any]]:
        """Get listeners.

        Returns:
            The requested listeners.
        """
        return [
            (name, getattr(self, method_name))
            for name, method_name in self.__cog_listeners__
        ]

    async def cog_load(self) -> None:
        """Cog load.

        Returns:
            None.
        """
        pass

    async def cog_unload(self) -> None:
        """Cog unload.

        Returns:
            None.
        """
        pass

    async def cog_command_error(self, ctx: Any, error: Exception) -> None:
        """Handle errors from this cog's commands; override it to use it.

        Runs after the command's own ``@command.error`` handler and before the
        bot's ``on_command_error``.

        Args:
            ctx: Invocation context of the failed command.
            error: The command error.

        Returns:
            None.
        """

    def has_error_handler(self) -> bool:
        """Return whether this cog overrides ``cog_command_error``.

        Returns:
            Whether the cog has its own command error handler.
        """
        return type(self).cog_command_error is not Cog.cog_command_error

    async def cog_before_invoke(self, ctx: Any) -> None:
        """Cog before invoke.

        Args:
            ctx: Command invocation context, including the author, channel, and guild.

        Returns:
            None.
        """
        pass

    async def cog_after_invoke(self, ctx: Any) -> None:
        """Cog after invoke.

        Args:
            ctx: Command invocation context, including the author, channel, and guild.

        Returns:
            None.
        """
        pass


__all__ = ("CogMeta", "Cog")
