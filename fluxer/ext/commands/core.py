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
    def __init__(self, func: Callable[..., Awaitable[Any]], **attrs: Any) -> None:
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Commands must be coroutine functions")
        self.callback = func
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
        return f"{self.parent.qualified_name} {self.name}" if self.parent else self.name

    @property
    def signature(self) -> str:
        params = list(self.clean_params.values())
        return " ".join(
            f"<{p.name}>" if p.default is inspect.Parameter.empty else f"[{p.name}]"
            for p in params
        )

    @property
    def params(self) -> OrderedDict[str, inspect.Parameter]:
        return OrderedDict(inspect.signature(self.callback).parameters)

    @property
    def clean_params(self) -> OrderedDict[str, inspect.Parameter]:
        params = list(self.params.values())
        if self.cog is not None and params:
            params = params[1:]
        if params and params[0].name == "ctx":
            params = params[1:]
        return OrderedDict((param.name, param) for param in params)

    @property
    def short_doc(self) -> str:
        if self.brief is not None:
            return self.brief
        return self.help.splitlines()[0] if self.help else ""

    def copy(self) -> "Command":
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
        self.checks.append(func)

    def remove_check(self, func: Check) -> None:
        try:
            self.checks.remove(func)
        except ValueError:
            pass

    def error(
        self, coro: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        self.error_handler = coro
        return coro

    def before_invoke(
        self, coro: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        self.before_invoke_hook = coro
        return coro

    def after_invoke(
        self, coro: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        self.after_invoke_hook = coro
        return coro

    async def can_run(self, ctx: Context) -> bool:
        for predicate in self.checks:
            if not await _maybe_await(predicate(ctx)):
                raise CheckFailure("A command check failed")
        return True

    async def prepare(self, ctx: Context) -> None:
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
    def __init__(self) -> None:
        self.all_commands: OrderedDict[str, Command] = OrderedDict()

    @property
    def commands(self) -> list[Command]:
        return list(dict.fromkeys(self.all_commands.values()))

    def add_command(self, command: Command) -> None:
        if isinstance(self, Group):
            command.parent = self
        self.all_commands[command.name] = command
        for alias in command.aliases:
            self.all_commands[alias] = command

    def remove_command(self, name: str) -> Command | None:
        command = self.all_commands.pop(name, None)
        if command:
            for alias in list(command.aliases):
                self.all_commands.pop(alias, None)
        return command

    def get_command(self, name: str) -> Command | None:
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
        out: list[Command] = []
        for command in self.commands:
            out.append(command)
            if isinstance(command, Group):
                out.extend(command.walk_commands())
        return out

    def command(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Awaitable[Any]]], Command]:
        def decorator(func: Callable[..., Awaitable[Any]]) -> Command:
            cmd = command(*args, **kwargs)(func)
            self.add_command(cmd)
            return cmd

        return decorator

    def group(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Awaitable[Any]]], "Group"]:
        def decorator(func: Callable[..., Awaitable[Any]]) -> Group:
            cmd = group(*args, **kwargs)(func)
            self.add_command(cmd)
            return cmd

        return decorator


class Group(GroupMixin, Command):
    def __init__(self, func: Callable[..., Awaitable[Any]], **attrs: Any) -> None:
        GroupMixin.__init__(self)
        Command.__init__(self, func, **attrs)
        self.invoke_without_command = attrs.get("invoke_without_command", False)

    def copy(self) -> "Group":
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
    def decorator(func: Callable[..., Awaitable[Any]]) -> Command:
        klass = cls or Command
        return klass(func, name=name, **attrs)

    return decorator


def group(
    name: str | None = None, **attrs: Any
) -> Callable[[Callable[..., Awaitable[Any]]], Group]:
    return command(name=name, cls=Group, **attrs)  # type: ignore[return-value]


def check(predicate: Check) -> Callable[[Any], Any]:
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
    async def predicate(ctx: Context) -> bool:
        for pred in checks:
            try:
                if await _maybe_await(pred(ctx)):
                    return True
            except Exception:
                pass
        return False

    return check(predicate)


def has_role(item: int | str) -> Callable[[Any], Any]:
    async def predicate(ctx: Context) -> bool:
        roles = getattr(ctx.author, "roles", [])
        role_ids = [getattr(r, "id", r) for r in roles]
        return item in role_ids or str(item) in {str(r) for r in role_ids}

    return check(predicate)


def has_any_role(*items: int | str) -> Callable[[Any], Any]:
    async def predicate(ctx: Context) -> bool:
        roles = getattr(ctx.author, "roles", [])
        role_ids = {str(getattr(r, "id", r)) for r in roles}
        return any(str(item) in role_ids for item in items)

    return check(predicate)


async def _check_fluxer_permissions(
    ctx: Context, user_id: int, perms: dict[str, bool]
) -> bool:
    from ...enums import Permissions
    from .errors import MissingPermissions

    if ctx.message.guild_id is None:
        return False
    if ctx.message._http is None:
        raise RuntimeError("HTTPClient is required to check permissions")

    guild_data, member_data, roles_data = await asyncio.gather(
        ctx.message._http.get_guild(ctx.message.guild_id),
        ctx.message._http.get_guild_member(ctx.message.guild_id, user_id),
        ctx.message._http.get_guild_roles(ctx.message.guild_id),
    )
    if user_id == int(guild_data["owner_id"]):
        return True

    role_ids = {int(role_id) for role_id in member_data.get("roles", [])}
    computed = Permissions(0)
    for role in roles_data:
        role_id = int(role["id"])
        if role_id == ctx.message.guild_id or role_id in role_ids:
            computed |= Permissions(int(role["permissions"]))
    if computed & Permissions.ADMINISTRATOR:
        return True

    missing = []
    for name, value in perms.items():
        perm = getattr(Permissions, name.upper(), None)
        if perm is None:
            missing.append(name)
            continue
        has_perm = bool(computed & perm)
        if has_perm != value:
            missing.append(name)
    if missing:
        raise MissingPermissions(missing)
    return True


def has_permissions(**perms: bool) -> Callable[[Any], Any]:
    async def predicate(ctx: Context) -> bool:
        return await _check_fluxer_permissions(ctx, ctx.author.id, perms)

    return check(predicate)


def has_guild_permissions(**perms: bool) -> Callable[[Any], Any]:
    return has_permissions(**perms)


def bot_has_permissions(**perms: bool) -> Callable[[Any], Any]:
    async def predicate(ctx: Context) -> bool:
        bot_user = ctx.bot.user
        if bot_user is None:
            return False
        return await _check_fluxer_permissions(ctx, bot_user.id, perms)

    return check(predicate)


def bot_has_guild_permissions(**perms: bool) -> Callable[[Any], Any]:
    return bot_has_permissions(**perms)


def bot_has_role(item: int | str) -> Callable[[Any], Any]:
    async def predicate(ctx: Context) -> bool:
        bot_user = ctx.bot.user
        roles = getattr(bot_user, "roles", []) if bot_user is not None else []
        role_ids = {str(getattr(role, "id", role)) for role in roles}
        return str(item) in role_ids

    return check(predicate)


def bot_has_any_role(*items: int | str) -> Callable[[Any], Any]:
    async def predicate(ctx: Context) -> bool:
        bot_user = ctx.bot.user
        roles = getattr(bot_user, "roles", []) if bot_user is not None else []
        role_ids = {str(getattr(role, "id", role)) for role in roles}
        return any(str(item) in role_ids for item in items)

    return check(predicate)


def is_nsfw() -> Callable[[Any], Any]:
    return check(lambda ctx: bool(getattr(ctx.channel, "nsfw", False)))


def guild_only() -> Callable[[Any], Any]:
    return check(lambda ctx: ctx.guild is not None)


def dm_only() -> Callable[[Any], Any]:
    return check(lambda ctx: ctx.guild is None)


def is_owner() -> Callable[[Any], Any]:
    async def predicate(ctx: Context) -> bool:
        return await ctx.bot.is_owner(ctx.author)

    return check(predicate)


def cooldown(
    rate: int, per: float, type: BucketType = BucketType.default
) -> Callable[[Any], Any]:
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
    def decorator(func: Any) -> Any:
        value = MaxConcurrency(number, per, wait=wait)
        if isinstance(func, Command):
            func._max_concurrency = value
        else:
            func.__commands_max_concurrency__ = value
        return func

    return decorator


def before_invoke(coro: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    setattr(coro, "__before_invoke__", True)
    return coro


def after_invoke(coro: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    setattr(coro, "__after_invoke__", True)
    return coro
