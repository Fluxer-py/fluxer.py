"""Bot helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Coroutine, TypeGuard, cast

from ...client import Client
from ...enums import Intents
from ...models import Message
from .context import Context
from .core import Command, GroupMixin, _maybe_await
from .errors import (
    CommandError,
    CommandNotFound,
    ExtensionAlreadyLoaded,
    ExtensionFailed,
    ExtensionNotFound,
    ExtensionNotLoaded,
    NoEntryPointError,
)
from .help import DefaultHelpCommand, HelpCommand
from .view import StringView

Prefix = (
    str
    | Iterable[str]
    | Callable[["Bot", Message], str | Iterable[str] | Awaitable[str | Iterable[str]]]
)
_default_help_command = object()


def _is_default_help_command(value: HelpCommand | None | object) -> TypeGuard[object]:
    return value is _default_help_command


def when_mentioned(bot: "Bot", message: Message, /) -> list[str]:
    """Return the bot mention prefixes accepted as command prefixes.

    Args:
        bot: Client owning this command, cog, or context.
        message: Message supplying content and channel/guild context.

    Returns:
        The result of this operation.
    """
    if bot.user is None:
        return []
    return [f"<@{bot.user.id}> ", f"<@!{bot.user.id}> "]


def when_mentioned_or(*prefixes: str) -> Callable[["Bot", Message], list[str]]:
    """Build a prefix resolver accepting mentions and the supplied prefixes.

    Args:
        *prefixes: Prefixes used by this operation.

    Returns:
        The configured decorator or callback wrapper.
    """

    def inner(bot: "Bot", message: Message) -> list[str]:
        return when_mentioned(bot, message) + list(prefixes)

    return inner


class Bot(GroupMixin, Client):
    """Bot data and behaviour.

    Attributes:
        description: Description.
        case_insensitive: Case insensitive.
        owner_id: Identity of the owning account when supplied by the object.
        owner_ids: Configured account IDs allowed to pass the bot-owner check.
        command_prefix: Command prefix used by this operation.
        commands: Commands.
        cogs: Cogs.
        extensions: Extensions.
        help_command: Help command.
    """

    description: str
    case_insensitive: bool
    owner_id: int | None
    owner_ids: set[int]

    def __init__(
        self,
        command_prefix: Prefix,
        *,
        help_command: HelpCommand | None | object = _default_help_command,
        description: str | None = None,
        intents: Intents | None = None,
        api_url: str | None = None,
        instance_url: str | None = None,
        max_retries: int = 4,
        retry_forever: bool = False,
        **options: Any,
    ) -> None:
        """Initialize the bot with the supplied configuration.

        Args:
            command_prefix: Command prefix used by this operation.
            help_command: Help command used by this operation.
            description: Descriptive text associated with this object.
            intents: Deprecated compatibility mask; Fluxer does not use intents to filter events.
            api_url: Already-versioned REST service override, including any instance path prefix.
            instance_url: Origin publishing the unauthenticated Fluxer discovery document.
            max_retries: Maximum retries after the initial request; zero disables retries.
            retry_forever: Whether replayable transient failures may retry without a ceiling.
            **options: Client configuration forwarded to the underlying gateway client.
        """
        Client.__init__(
            self,
            intents=intents,
            api_url=api_url,
            instance_url=instance_url,
            max_retries=max_retries,
            retry_forever=retry_forever,
            max_messages=int(options.get("max_messages", 1000)),
            cache_members=bool(options.get("cache_members", True)),
        )
        GroupMixin.__init__(self)
        self.command_prefix: Prefix = command_prefix
        self.description = description or ""
        self.case_insensitive = bool(options.get("case_insensitive", False))
        self.owner_id = options.get("owner_id")
        self.owner_ids = set(options.get("owner_ids", ()))
        self._checks: list[Callable[[Context], Any]] = []
        self._check_once: list[Callable[[Context], Any]] = []
        self._listeners: dict[str, list[Callable[..., Awaitable[Any]]]] = {}
        self._cogs: dict[str, Any] = {}
        self._extensions: dict[str, Any] = {}
        self._before_invoke: Callable[[Context], Awaitable[Any]] | None = None
        self._after_invoke: Callable[[Context], Awaitable[Any]] | None = None
        self._help_command: HelpCommand | None = None
        if _is_default_help_command(help_command):
            help_command = DefaultHelpCommand()
        self.help_command = cast(HelpCommand | None, help_command)

    @property
    def commands(self) -> list[Command]:
        """Commands.

        Returns:
            The result of this operation.
        """
        return GroupMixin.commands.fget(self)  # type: ignore[attr-defined]

    @property
    def cogs(self) -> dict[str, Any]:
        """Cogs.

        Returns:
            The result of this operation.
        """
        return self._cogs.copy()

    @property
    def extensions(self) -> dict[str, Any]:
        """Extensions.

        Returns:
            The result of this operation.
        """
        return self._extensions.copy()

    @property
    def help_command(self) -> HelpCommand | None:
        """Help command.

        Returns:
            The result of this operation.
        """
        return self._help_command

    @help_command.setter
    def help_command(self, value: HelpCommand | None) -> None:
        """Help command.

        Args:
            value: Value to convert, assign, or compare.

        Returns:
            None.
        """
        if value is not None and not isinstance(value, HelpCommand):
            raise TypeError("help_command must be a HelpCommand or None")
        if self._help_command is not None:
            self._help_command._remove_from_bot(self)
        self._help_command = value
        if value is not None:
            value._add_to_bot(self)

    def dispatch(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Dispatch.

        Args:
            event_name: Event name dispatched to registered callbacks.
            *args: Positional arguments forwarded to the wrapped callback.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            None.
        """
        self._listeners.setdefault(event_name, [])
        for listener in list(self._listeners[event_name]):
            self.loop_create_task(listener(*args, **kwargs))

    def loop_create_task(self, coro: Awaitable[Any]) -> None:
        """Loop create task.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            None.
        """
        import asyncio

        asyncio.create_task(cast(Coroutine[Any, Any, Any], coro))

    def add_listener(
        self, func: Callable[..., Awaitable[Any]], name: str | None = None
    ) -> None:
        """Add listener.

        Args:
            func: Callable registered or applied by this helper.
            name: Name to assign or resolve in this operation.

        Returns:
            None.
        """
        self._listeners.setdefault(name or func.__name__, []).append(func)
        self._event_handlers.setdefault(name or func.__name__, []).append(
            cast(Callable[..., Coroutine[Any, Any, None]], func)
        )

    def remove_listener(
        self, func: Callable[..., Awaitable[Any]], name: str | None = None
    ) -> None:
        """Remove listener.

        Args:
            func: Callable registered or applied by this helper.
            name: Name to assign or resolve in this operation.

        Returns:
            None.
        """
        listeners = self._listeners.get(name or func.__name__, [])
        if func in listeners:
            listeners.remove(func)
        handlers = self._event_handlers.get(name or func.__name__, [])
        handler = cast(Callable[..., Coroutine[Any, Any, None]], func)
        if handler in handlers:
            handlers.remove(handler)

    def listen(
        self, name: str | None = None
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Register a coroutine as a listener for the selected event.

        Args:
            name: Name to assign or resolve in this operation.

        Returns:
            The configured decorator or callback wrapper.
        """

        def decorator(
            func: Callable[..., Awaitable[Any]],
        ) -> Callable[..., Awaitable[Any]]:
            self.add_listener(func, name)
            return func

        return decorator

    def check(self, func: Callable[[Context], Any]) -> Callable[[Context], Any]:
        """Register a condition that must pass before command invocation.

        Args:
            func: Callable registered or applied by this helper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self.add_check(func)
        return func

    def add_check(
        self, func: Callable[[Context], Any], *, call_once: bool = False
    ) -> None:
        """Add check.

        Args:
            func: Callable registered or applied by this helper.
            call_once: Call once used by this operation.

        Returns:
            None.
        """
        (self._check_once if call_once else self._checks).append(func)

    def remove_check(
        self, func: Callable[[Context], Any], *, call_once: bool = False
    ) -> None:
        """Remove check.

        Args:
            func: Callable registered or applied by this helper.
            call_once: Call once used by this operation.

        Returns:
            None.
        """
        target = self._check_once if call_once else self._checks
        if func in target:
            target.remove(func)

    def check_once(self, func: Callable[[Context], Any]) -> Callable[[Context], Any]:
        """Register a condition evaluated once for a command invocation.

        Args:
            func: Callable registered or applied by this helper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self.add_check(func, call_once=True)
        return func

    async def can_run(self, ctx: Context, *, call_once: bool = False) -> bool:
        """Evaluate the configured checks for this invocation.

        Args:
            ctx: Command invocation context, including the author, channel, and guild.
            call_once: Call once used by this operation.

        Returns:
            Whether the documented condition holds for the current state.
        """
        checks = self._check_once if call_once else self._checks
        return all([await _maybe_await(check(ctx)) for check in checks])

    async def is_owner(self, user: Any) -> bool:
        """Check whether the invocation author is a configured bot owner.

        Args:
            user: User object or identity used by the operation.

        Returns:
            Whether the documented condition holds for the current state.
        """
        user_id = getattr(user, "id", None)
        if self.owner_id is not None:
            return user_id == self.owner_id
        if self.owner_ids:
            return user_id in self.owner_ids
        return self.user is not None and user_id == self.user.id

    def before_invoke(
        self, coro: Callable[[Context], Awaitable[Any]]
    ) -> Callable[[Context], Awaitable[Any]]:
        """Register the coroutine run immediately before command execution.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self._before_invoke = coro
        return coro

    def after_invoke(
        self, coro: Callable[[Context], Awaitable[Any]]
    ) -> Callable[[Context], Awaitable[Any]]:
        """Register the coroutine run after command execution.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self._after_invoke = coro
        return coro

    async def get_prefix(self, message: Message) -> str | Iterable[str]:
        """Resolve the command prefixes applicable to this message.

        Args:
            message: Message supplying content and channel/guild context.

        Returns:
            The requested prefix.
        """
        prefix = self.command_prefix
        if callable(prefix):
            value = prefix(self, message)
            return await value if inspect.isawaitable(value) else value
        return prefix

    async def get_context(
        self, message: Any, *, cls: type[Context] = Context
    ) -> Context:
        """Build command context by resolving the message prefix and command.

        Args:
            cls: Context subclass to instantiate for this invocation.
            message: Message supplying content and channel/guild context.

        Returns:
            The requested context.
        """
        prefixes = await self.get_prefix(cast(Message, message))
        view = StringView(message.content or "")
        normalized_prefixes = (
            [prefixes] if isinstance(prefixes, str) else list(prefixes)
        )
        prefix = view.find_prefix(normalized_prefixes)
        ctx = cls(bot=self, message=message, prefix=prefix, view=view)
        if prefix is None:
            return ctx
        view.index = len(prefix)
        view.skip_ws()
        invoked = view.get_word()
        lookup = invoked.lower() if self.case_insensitive else invoked
        command = self.all_commands.get(lookup)
        ctx.invoked_with = invoked
        ctx.command = command
        return ctx

    async def invoke(self, ctx: Context) -> None:
        """Invoke the selected command with its parsed context.

        Args:
            ctx: Command invocation context, including the author, channel, and guild.

        Returns:
            None.
        """
        if ctx.command is None:
            if ctx.invoked_with:
                await self.on_command_error(ctx, CommandNotFound(ctx.invoked_with))
            return
        try:
            if not await self.can_run(ctx, call_once=True):
                return
            await ctx.command.invoke(ctx)
        except CommandError as exc:
            await self.on_command_error(ctx, exc)

    async def process_commands(self, message: Message) -> None:
        """Resolve and invoke the command contained in a message.

        Args:
            message: Message supplying content and channel/guild context.

        Returns:
            None.
        """
        if getattr(message.author, "bot", False):
            return
        ctx = await self.get_context(message)
        await self.invoke(ctx)

    async def on_command_error(self, context: Context, exception: Exception) -> None:
        """On command error.

        Args:
            context: Command invocation context used for parsing and output.
            exception: Exception used by this operation.

        Returns:
            None.
        """
        import logging

        logging.getLogger(__name__).exception(
            "Ignoring exception in command %s", context.command, exc_info=exception
        )

    async def _dispatch(self, event_name: str, data: Any) -> None:
        await super()._dispatch(event_name, data)
        if event_name == "MESSAGE_CREATE":
            message = self._parse_message(data)
            await self.process_commands(message)

    async def add_cog(self, cog: Any) -> None:
        """Add cog.

        Args:
            cog: Cog containing related commands and listeners.

        Returns:
            None.
        """
        name = (
            cog.qualified_name
            if hasattr(cog, "qualified_name")
            else cog.__class__.__name__
        )
        if name in self._cogs:
            raise ValueError(f"Cog {name!r} is already loaded")
        self._cogs[name] = cog
        for command in cog.get_commands():
            bound = command.copy()
            bound.cog = cog
            for child in (
                bound.walk_commands() if hasattr(bound, "walk_commands") else [bound]
            ):
                child.cog = cog
            self.add_command(bound)
        for listener_name, listener in cog.get_listeners():
            self.add_listener(listener, listener_name)
        await cog.cog_load()

    def get_cog(self, name: str) -> Any | None:
        """Get cog.

        Args:
            name: Name to assign or resolve in this operation.

        Returns:
            The requested cog, or None when no matching value is available.
        """
        return self._cogs.get(name)

    async def remove_cog(self, name: str) -> Any | None:
        """Remove cog.

        Args:
            name: Name to assign or resolve in this operation.

        Returns:
            The result of this operation.
        """
        cog = self._cogs.pop(name, None)
        if cog is None:
            return None
        if self.help_command is not None and self.help_command.cog is cog:
            self.help_command.cog = None
        await cog.cog_unload()
        for command in cog.get_commands():
            self.remove_command(command.name)
        for listener_name, listener in cog.get_listeners():
            self.remove_listener(listener, listener_name)
        return cog

    async def load_extension(self, name: str, *, package: str | None = None) -> None:
        """Load extension.

        Args:
            name: Name to assign or resolve in this operation.
            package: Package used by this operation.

        Returns:
            None.
        """
        if name in self._extensions:
            raise ExtensionAlreadyLoaded(name=name)
        try:
            module = importlib.import_module(name, package)
        except ModuleNotFoundError as exc:
            raise ExtensionNotFound(str(exc), name=name) from exc
        setup = getattr(module, "setup", None)
        if setup is None:
            raise NoEntryPointError(name=name)
        try:
            result = setup(self)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            raise ExtensionFailed(name, exc) from exc
        self._extensions[name] = module

    async def unload_extension(self, name: str) -> None:
        """Unload extension.

        Args:
            name: Name to assign or resolve in this operation.

        Returns:
            None.
        """
        if name not in self._extensions:
            raise ExtensionNotLoaded(name=name)
        module = self._extensions.pop(name)
        teardown = getattr(module, "teardown", None)
        if teardown:
            result = teardown(self)
            if inspect.isawaitable(result):
                await result
        sys.modules.pop(name, None)

    async def reload_extension(self, name: str, *, package: str | None = None) -> None:
        """Reload extension.

        Args:
            name: Name to assign or resolve in this operation.
            package: Package used by this operation.

        Returns:
            None.
        """
        await self.unload_extension(name)
        await self.load_extension(name, package=package)


class AutoShardedBot(Bot):
    """Bot variant reserved for Fluxer gateway shard metadata.

    Attributes:
        description: Description.
        case_insensitive: Case insensitive.
        owner_id: Identity of the owning account when supplied by the object.
        owner_ids: Configured account IDs allowed to pass the bot-owner check.
        command_prefix: Command prefix used by this operation.
        commands: Commands.
        cogs: Cogs.
        extensions: Extensions.
        help_command: Help command.
    """

    pass


__all__ = ("when_mentioned", "when_mentioned_or", "Bot", "AutoShardedBot")
