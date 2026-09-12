"""Core helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import asyncio
import inspect
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any, get_type_hints

from .context import Context
from .converter import _Greedy, run_converter
from .cooldowns import BucketType, CooldownMapping, MaxConcurrency
from .errors import (
    CheckFailure,
    CommandInvokeError,
    CommandNotFound,
    CommandOnCooldown,
    DisabledCommand,
    MissingRequiredArgument,
)
from .view import StringView

Check = Callable[[Context], bool | Awaitable[bool]]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class Command:
    """Async command callback, argument parsing, and invocation checks.

    Attributes:
        name: Name.
        aliases: Aliases.
        help: Help.
        brief: Brief.
        description: Description.
        enabled: Enabled.
        hidden: Hidden.
        callback: Async callable invoked by this command or task.
        checks: Alternative conditions evaluated by the check decorator.
        cog: Cog containing related commands and listeners.
        parent: Owning group for this command.
        error_handler: Error handler used by this operation.
        before_invoke_hook: Before invoke hook used by this operation.
        after_invoke_hook: After invoke hook used by this operation.
        qualified_name: Return the name including the owning command groups.
        signature: Return the user-facing command argument signature.
        params: Return the command callback's inspected parameters.
        clean_params: Return callback parameters excluding context and bound-instance arguments.
        short_doc: Return the brief description or first line of command help.
    """

    name: str
    aliases: list[str]
    help: str
    brief: str | None
    description: str
    enabled: bool
    hidden: bool

    def __init__(self, func: Callable[..., Awaitable[Any]], **attrs: Any) -> None:
        """Initialize the command with the supplied configuration.

        Args:
            func: Callable registered or applied by this helper.
            **attrs: Attrs used by this operation.
        """
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Commands must be coroutine functions")
        self.callback: Callable[..., Awaitable[Any]] = func
        self.name = attrs.get("name") or func.__name__
        self.aliases = list(attrs.get("aliases", ()))
        self.help = attrs.get("help") or inspect.getdoc(func) or ""
        self.brief = attrs.get("brief")
        self.description = attrs.get("description") or ""
        self.enabled = attrs.get("enabled", True)
        self.hidden = attrs.get("hidden", False)
        self.checks: list[Check] = list(getattr(func, "__commands_checks__", ()))
        self._buckets: CooldownMapping = getattr(
            func, "__commands_cooldown__", CooldownMapping(None)
        )
        self._max_concurrency: MaxConcurrency | None = getattr(
            func, "__commands_max_concurrency__", None
        )
        self.cog: Any = None
        self.parent: Group | None = None
        self.error_handler: Callable[..., Awaitable[Any]] | None = None
        self.before_invoke_hook: Callable[..., Awaitable[Any]] | None = None
        self.after_invoke_hook: Callable[..., Awaitable[Any]] | None = None

    @property
    def qualified_name(self) -> str:
        """Return the name including the owning command groups.

        Returns:
            The result of this operation.
        """
        return f"{self.parent.qualified_name} {self.name}" if self.parent else self.name

    @property
    def signature(self) -> str:
        """Return the user-facing command argument signature.

        Returns:
            The result of this operation.
        """
        params = list(self.clean_params.values())
        return " ".join(
            f"<{p.name}>" if p.default is inspect.Parameter.empty else f"[{p.name}]"
            for p in params
        )

    @property
    def params(self) -> OrderedDict[str, inspect.Parameter]:
        """Return the command callback's inspected parameters.

        Returns:
            The result of this operation.
        """
        return OrderedDict(inspect.signature(self.callback).parameters)

    @property
    def clean_params(self) -> OrderedDict[str, inspect.Parameter]:
        """Return callback parameters excluding context and bound-instance arguments.

        Returns:
            The result of this operation.
        """
        params = list(self.params.values())
        if self.cog is not None and params:
            params = params[1:]
        if params and params[0].name == "ctx":
            params = params[1:]
        return OrderedDict((param.name, param) for param in params)

    @property
    def short_doc(self) -> str:
        """Return the brief description or first line of command help.

        Returns:
            The result of this operation.
        """
        if self.brief is not None:
            return self.brief
        return self.help.splitlines()[0] if self.help else ""

    def copy(self) -> "Command":
        """Copy.

        Returns:
            The result of this operation.
        """
        copied = type(self)(
            self.callback,
            name=self.name,
            aliases=self.aliases,
            help=self.help,
            brief=self.brief,
            description=self.description,
            enabled=self.enabled,
            hidden=self.hidden,
        )
        copied.checks = self.checks.copy()
        copied._buckets = self._buckets.copy()
        copied._max_concurrency = (
            self._max_concurrency.copy() if self._max_concurrency else None
        )
        return copied

    def add_check(self, func: Check) -> None:
        """Add check.

        Args:
            func: Callable registered or applied by this helper.

        Returns:
            None.
        """
        self.checks.append(func)

    def remove_check(self, func: Check) -> None:
        """Remove check.

        Args:
            func: Callable registered or applied by this helper.

        Returns:
            None.
        """
        try:
            self.checks.remove(func)
        except ValueError:
            pass

    def error(
        self, coro: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        """Error.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self.error_handler = coro
        return coro

    def before_invoke(
        self, coro: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        """Register the coroutine run immediately before command execution.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self.before_invoke_hook = coro
        return coro

    def after_invoke(
        self, coro: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        """Register the coroutine run after command execution.

        Args:
            coro: Coroutine function invoked by the task or command wrapper.

        Returns:
            The configured decorator or callback wrapper.
        """
        self.after_invoke_hook = coro
        return coro

    async def can_run(self, ctx: Context) -> bool:
        """Evaluate the configured checks for this invocation.

        Args:
            ctx: Command invocation context, including the author, channel, and guild.

        Returns:
            Whether the documented condition holds for the current state.
        """
        for predicate in self.checks:
            if not await _maybe_await(predicate(ctx)):
                raise CheckFailure("A command check failed")
        return True

    async def prepare(self, ctx: Context) -> None:
        """Prepare arguments, checks, and cooldown state for command invocation.

        Args:
            ctx: Command invocation context, including the author, channel, and guild.

        Returns:
            None.
        """
        if not self.enabled:
            raise DisabledCommand(f"{self.qualified_name} is disabled")
        await self.can_run(ctx)
        retry_after = self._buckets.update_rate_limit(ctx.message)
        if retry_after:
            raise CommandOnCooldown(self._buckets, retry_after)
        if self._max_concurrency is not None:
            await self._max_concurrency.acquire(ctx.message)

    async def _parse_arguments(self, ctx: Context) -> None:
        params = list(inspect.signature(self.callback).parameters.values())
        try:
            type_hints = get_type_hints(self.callback)
        except Exception:
            type_hints = {}
        call_args: list[Any] = []
        if self.cog is not None:
            call_args.append(self.cog)
            params = params[1:]
        if params and params[0].name == "ctx":
            call_args.append(ctx)
            params = params[1:]
        if ctx.view is None:
            raise RuntimeError("Command context is missing a parser view")
        view: StringView = ctx.view
        call_kwargs: dict[str, Any] = {}

        for param in params:
            if param.kind is inspect.Parameter.VAR_POSITIONAL:
                values = []
                while True:
                    arg = view.get_quoted_word()
                    if not arg:
                        break
                    values.append(
                        await run_converter(
                            ctx, type_hints.get(param.name, param.annotation), arg
                        )
                    )
                call_args.extend(values)
                continue

            if param.kind is inspect.Parameter.KEYWORD_ONLY:
                rest = view.read_rest().strip()
                if not rest and param.default is inspect.Parameter.empty:
                    raise MissingRequiredArgument(param)
                if rest:
                    call_kwargs[param.name] = await run_converter(
                        ctx, type_hints.get(param.name, param.annotation), rest
                    )
                continue

            converter = type_hints.get(param.name, param.annotation)
            if isinstance(converter, _Greedy):
                values = []
                while True:
                    old = view.index
                    arg = view.get_quoted_word()
                    if not arg:
                        break
                    try:
                        values.append(
                            await run_converter(ctx, converter.converter, arg)
                        )
                    except Exception:
                        view.index = old
                        break
                call_args.append(values)
                continue

            arg = view.get_quoted_word()
            if not arg:
                if param.default is inspect.Parameter.empty:
                    raise MissingRequiredArgument(param)
                call_args.append(param.default)
            else:
                call_args.append(await run_converter(ctx, converter, arg))

        ctx.args = call_args
        ctx.kwargs = call_kwargs

    async def invoke(self, ctx: Context) -> Any:
        """Invoke the selected command with its parsed context.

        Args:
            ctx: Command invocation context, including the author, channel, and guild.

        Returns:
            The result of this operation.
        """
        ctx.command = self
        acquired = self._max_concurrency is not None
        try:
            await self.prepare(ctx)
            await self._parse_arguments(ctx)
            if ctx.bot._before_invoke:
                await ctx.bot._before_invoke(ctx)
            if self.before_invoke_hook:
                await self.before_invoke_hook(ctx)
            result = await self.callback(*ctx.args, **ctx.kwargs)
            if self.after_invoke_hook:
                await self.after_invoke_hook(ctx)
            if ctx.bot._after_invoke:
                await ctx.bot._after_invoke(ctx)
            return result
        except Exception as exc:
            if self.error_handler:
                return await self.error_handler(ctx, exc)
            raise (
                CommandInvokeError(exc)
                if not isinstance(
                    exc,
                    (
                        DisabledCommand,
                        CheckFailure,
                        CommandOnCooldown,
                        MissingRequiredArgument,
                    ),
                )
                else exc
            )
        finally:
            if acquired and self._max_concurrency:
                await self._max_concurrency.release(ctx.message)


class GroupMixin:
    """Registration and lookup shared by bot and group command containers.

    Attributes:
        all_commands: All commands used by this operation.
        commands: Commands.
    """

    def __init__(self) -> None:
        """Initialize the group mixin with the supplied configuration.

        Note:
            Further behaviour is defined by the methods on this instance.
        """
        self.all_commands: OrderedDict[str, Command] = OrderedDict()

    @property
    def commands(self) -> list[Command]:
        """Commands.

        Returns:
            The result of this operation.
        """
        return list(dict.fromkeys(self.all_commands.values()))

    def add_command(self, command: Command) -> None:
        """Add command.

        Args:
            command: Command to resolve, invoke, or display.

        Returns:
            None.
        """
        if isinstance(self, Group):
            command.parent = self
        self.all_commands[command.name] = command
        for alias in command.aliases:
            self.all_commands[alias] = command

    def remove_command(self, name: str) -> Command | None:
        """Remove command.

        Args:
            name: Name to assign or resolve in this operation.

        Returns:
            The result of this operation.
        """
        command = self.all_commands.pop(name, None)
        if command:
            for alias in list(command.aliases):
                self.all_commands.pop(alias, None)
        return command

    def get_command(self, name: str) -> Command | None:
        """Get command.

        Args:
            name: Name to assign or resolve in this operation.

        Returns:
            The requested command, or None when no matching value is available.
        """
        current: Command | None = None
        mapping: GroupMixin = self
        for part in name.split():
            current = mapping.all_commands.get(part)
            if current is None:
                return None
            if isinstance(current, Group):
                mapping = current
        return current

    def walk_commands(self) -> list[Command]:
        """Walk commands.

        Returns:
            The result of this operation.
        """
        out: list[Command] = []
        for command in self.commands:
            out.append(command)
            if isinstance(command, Group):
                out.extend(command.walk_commands())
        return out

    def command(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Awaitable[Any]]], Command]:
        """Command.

        Args:
            *args: Positional arguments forwarded to the wrapped callback.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The configured decorator or callback wrapper.
        """

        def decorator(func: Callable[..., Awaitable[Any]]) -> Command:
            cmd = command(*args, **kwargs)(func)
            self.add_command(cmd)
            return cmd

        return decorator

    def group(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Awaitable[Any]]], "Group"]:
        """Group.

        Args:
            *args: Positional arguments forwarded to the wrapped callback.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The configured decorator or callback wrapper.
        """

        def decorator(func: Callable[..., Awaitable[Any]]) -> Group:
            cmd = group(*args, **kwargs)(func)
            self.add_command(cmd)
            return cmd

        return decorator


class Group(GroupMixin, Command):
    """Command that owns subcommands and their invocation policy.

    Attributes:
        all_commands: All commands used by this operation.
        commands: Commands.
        name: Name.
        aliases: Aliases.
        help: Help.
        brief: Brief.
        description: Description.
        enabled: Enabled.
        hidden: Hidden.
        callback: Async callable invoked by this command or task.
        checks: Alternative conditions evaluated by the check decorator.
        cog: Cog containing related commands and listeners.
        parent: Owning group for this command.
        error_handler: Error handler used by this operation.
        before_invoke_hook: Before invoke hook used by this operation.
        after_invoke_hook: After invoke hook used by this operation.
        qualified_name: Return the name including the owning command groups.
        signature: Return the user-facing command argument signature.
        params: Return the command callback's inspected parameters.
        clean_params: Return callback parameters excluding context and bound-instance arguments.
        short_doc: Return the brief description or first line of command help.
        invoke_without_command: Invoke without command.
    """

    invoke_without_command: bool

    def __init__(self, func: Callable[..., Awaitable[Any]], **attrs: Any) -> None:
        """Initialize the group with the supplied configuration.

        Args:
            func: Callable registered or applied by this helper.
            **attrs: Attrs used by this operation.
        """
        GroupMixin.__init__(self)
        Command.__init__(self, func, **attrs)
        self.invoke_without_command = attrs.get("invoke_without_command", False)

    def copy(self) -> "Group":
        """Copy.

        Returns:
            The result of this operation.
        """
        copied = type(self)(
            self.callback,
            name=self.name,
            aliases=self.aliases,
            help=self.help,
            brief=self.brief,
            description=self.description,
            enabled=self.enabled,
            hidden=self.hidden,
            invoke_without_command=self.invoke_without_command,
        )
        copied.checks = self.checks.copy()
        copied._buckets = self._buckets.copy()
        copied._max_concurrency = (
            self._max_concurrency.copy() if self._max_concurrency else None
        )
        for command in self.commands:
            copied.add_command(command.copy())
        return copied

    async def invoke(self, ctx: Context) -> Any:
        """Invoke the selected command with its parsed context.

        Args:
            ctx: Command invocation context, including the author, channel, and guild.

        Returns:
            The result of this operation.
        """
        if ctx.view is None:
            raise RuntimeError("Command context is missing a parser view")
        view = ctx.view
        view.skip_ws()
        old = view.index
        trigger = view.get_word()
        subcommand = self.all_commands.get(trigger)
        if subcommand is not None:
            subcommand.parent = self
            return await subcommand.invoke(ctx)
        view.index = old
        if self.invoke_without_command:
            return await super().invoke(ctx)
        raise CommandNotFound(trigger)


def command(
    name: str | None = None, cls: type[Command] | None = None, **attrs: Any
) -> Callable[[Callable[..., Awaitable[Any]]], Command]:
    """Command.

    Args:
        cls: Command subclass to construct; omission uses Command.
        name: Name to assign or resolve in this operation.
        **attrs: Attrs used by this operation.

    Returns:
        The configured decorator or callback wrapper.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Command:
        klass = cls or Command
        return klass(func, name=name, **attrs)

    return decorator


def group(
    name: str | None = None, **attrs: Any
) -> Callable[[Callable[..., Awaitable[Any]]], Group]:
    """Group.

    Args:
        name: Name to assign or resolve in this operation.
        **attrs: Attrs used by this operation.

    Returns:
        The configured decorator or callback wrapper.
    """
    return command(name=name, cls=Group, **attrs)  # type: ignore[return-value]


def check(predicate: Check) -> Callable[[Any], Any]:
    """Register a condition that must pass before command invocation.

    Args:
        predicate: Condition used to accept an item or permit execution.

    Returns:
        The configured decorator or callback wrapper.
    """

    def decorator(func: Any) -> Any:
        if isinstance(func, Command):
            func.checks.append(predicate)
        else:
            checks = getattr(func, "__commands_checks__", [])
            checks.append(predicate)
            func.__commands_checks__ = checks
        return func

    return decorator


def check_any(*checks: Check) -> Callable[[Any], Any]:
    """Accept an invocation when at least one supplied check passes.

    Args:
        *checks: Alternative conditions evaluated by the check decorator.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        for pred in checks:
            try:
                if await _maybe_await(pred(ctx)):
                    return True
            except Exception:
                pass
        return False

    return check(predicate)


async def _member_has_role(
    ctx: Context, user_id: int, items: tuple[int | str, ...]
) -> bool:
    if ctx.message.guild_id is None:
        return False
    http = ctx.message._http
    if http is None:
        raise RuntimeError("HTTPClient is required to check roles")
    member = await http.get_guild_member(ctx.message.guild_id, user_id)
    role_ids = {int(role_id) for role_id in member.get("roles", [])}
    roles = await http.get_guild_roles(ctx.message.guild_id)
    names = {role["name"] for role in roles if int(role["id"]) in role_ids}
    return any(
        (isinstance(item, int) and item in role_ids)
        or (
            isinstance(item, str)
            and (item in names or item in {str(r) for r in role_ids})
        )
        for item in items
    )


def has_role(item: int | str) -> Callable[[Any], Any]:
    """Require a guild member to hold the specified role name or ID.

    Args:
        item: Role name or ID required by this check.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return await _member_has_role(ctx, ctx.author.id, (item,))

    return check(predicate)


def has_any_role(*items: int | str) -> Callable[[Any], Any]:
    """Require a guild member to hold at least one specified role.

    Args:
        *items: Alternative role names or IDs accepted by this check.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return await _member_has_role(ctx, ctx.author.id, items)

    return check(predicate)


async def _check_fluxer_permissions(
    ctx: Context,
    user_id: int,
    perms: dict[str, bool],
    *,
    guild_only: bool = False,
) -> bool:
    from ...enums import Permissions
    from ...permissions import _effective_permissions
    from .errors import MissingPermissions

    unknown = set(name for name in perms if name.upper() not in Permissions.__members__)
    if unknown:
        raise ValueError(f"Unknown permissions: {', '.join(sorted(unknown))}")
    if ctx.message.guild_id is None:
        return False
    http = ctx.message._http
    if http is None:
        raise RuntimeError("HTTPClient is required to check permissions")
    guild, member, roles = await asyncio.gather(
        http.get_guild(ctx.message.guild_id),
        http.get_guild_member(ctx.message.guild_id, user_id),
        http.get_guild_roles(ctx.message.guild_id),
    )
    channel = None if guild_only else await http.get_channel(ctx.message.channel_id)
    computed = _effective_permissions(guild, member, roles, user_id, channel)
    missing = [
        name
        for name, required in perms.items()
        if bool(computed & Permissions[name.upper()]) != required
    ]
    if missing:
        raise MissingPermissions(missing)
    return True


def has_permissions(**perms: bool) -> Callable[[Any], Any]:
    """Check the caller's effective permissions after channel overwrites.

    Args:
        **perms: Permission names and required boolean values; unknown names are rejected.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return await _check_fluxer_permissions(ctx, ctx.author.id, perms)

    return check(predicate)


def has_guild_permissions(**perms: bool) -> Callable[[Any], Any]:
    """Check the caller's guild role permissions without channel overwrites.

    Args:
        **perms: Permission names and required boolean values; unknown names are rejected.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return await _check_fluxer_permissions(
            ctx, ctx.author.id, perms, guild_only=True
        )

    return check(predicate)


def bot_has_permissions(**perms: bool) -> Callable[[Any], Any]:
    """Check the bot member's effective channel permissions.

    Args:
        **perms: Permission names and required boolean values; unknown names are rejected.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return ctx.bot.user is not None and await _check_fluxer_permissions(
            ctx, ctx.bot.user.id, perms
        )

    return check(predicate)


def bot_has_guild_permissions(**perms: bool) -> Callable[[Any], Any]:
    """Check the bot member's guild permissions without channel overwrites.

    Args:
        **perms: Permission names and required boolean values; unknown names are rejected.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return ctx.bot.user is not None and await _check_fluxer_permissions(
            ctx, ctx.bot.user.id, perms, guild_only=True
        )

    return check(predicate)


def bot_has_role(item: int | str) -> Callable[[Any], Any]:
    """Require the bot's guild member to hold the specified role.

    Args:
        item: Role name or ID required by this check.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return ctx.bot.user is not None and await _member_has_role(
            ctx, ctx.bot.user.id, (item,)
        )

    return check(predicate)


def bot_has_any_role(*items: int | str) -> Callable[[Any], Any]:
    """Require the bot's guild member to hold at least one specified role.

    Args:
        *items: Alternative role names or IDs accepted by this check.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return ctx.bot.user is not None and await _member_has_role(
            ctx, ctx.bot.user.id, items
        )

    return check(predicate)


def is_nsfw() -> Callable[[Any], Any]:
    """Restrict invocation to a channel marked as mature content.

    Returns:
        The configured decorator or callback wrapper.
    """
    return check(lambda ctx: bool(getattr(ctx.channel, "nsfw", False)))


def guild_only() -> Callable[[Any], Any]:
    """Restrict command invocation to guild channels.

    Returns:
        The configured decorator or callback wrapper.
    """
    return check(lambda ctx: ctx.guild is not None)


def dm_only() -> Callable[[Any], Any]:
    """Restrict command invocation to private channels.

    Returns:
        The configured decorator or callback wrapper.
    """
    return check(lambda ctx: ctx.guild is None)


def is_owner() -> Callable[[Any], Any]:
    """Check whether the invocation author is a configured bot owner.

    Returns:
        The configured decorator or callback wrapper.
    """

    async def predicate(ctx: Context) -> bool:
        return await ctx.bot.is_owner(ctx.author)

    return check(predicate)


def cooldown(
    rate: int, per: float, type: BucketType = BucketType.default
) -> Callable[[Any], Any]:
    """Apply a local command cooldown independent of Fluxer HTTP limits.

    Args:
        rate: Number of uses permitted during the local cooldown interval.
        per: Length of the local cooldown interval in seconds.
        type: Type used by this operation.

    Returns:
        The configured decorator or callback wrapper.
    """

    def decorator(func: Any) -> Any:
        mapping = CooldownMapping.from_cooldown(rate, per, type)
        if isinstance(func, Command):
            func._buckets = mapping
        else:
            func.__commands_cooldown__ = mapping
        return func

    return decorator


def max_concurrency(
    number: int, per: BucketType = BucketType.default, *, wait: bool = False
) -> Callable[[Any], Any]:
    """Bound concurrent invocations within the selected command bucket.

    Args:
        number: Maximum concurrent command invocations allowed for a bucket.
        per: Length of the local cooldown interval in seconds.
        wait: Whether to return the created webhook message instead of an empty response.

    Returns:
        The configured decorator or callback wrapper.
    """

    def decorator(func: Any) -> Any:
        value = MaxConcurrency(number, per, wait=wait)
        if isinstance(func, Command):
            func._max_concurrency = value
        else:
            func.__commands_max_concurrency__ = value
        return func

    return decorator


def before_invoke(coro: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Register the coroutine run immediately before command execution.

    Args:
        coro: Coroutine function invoked by the task or command wrapper.

    Returns:
        The configured decorator or callback wrapper.
    """
    setattr(coro, "__before_invoke__", True)
    return coro


def after_invoke(coro: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Register the coroutine run after command execution.

    Args:
        coro: Coroutine function invoked by the task or command wrapper.

    Returns:
        The configured decorator or callback wrapper.
    """
    setattr(coro, "__after_invoke__", True)
    return coro


__all__ = (
    "Command",
    "GroupMixin",
    "Group",
    "command",
    "group",
    "check",
    "check_any",
    "has_role",
    "has_any_role",
    "has_permissions",
    "has_guild_permissions",
    "bot_has_permissions",
    "bot_has_guild_permissions",
    "bot_has_role",
    "bot_has_any_role",
    "is_nsfw",
    "guild_only",
    "dm_only",
    "is_owner",
    "cooldown",
    "max_concurrency",
    "before_invoke",
    "after_invoke",
)
