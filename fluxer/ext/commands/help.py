from __future__ import annotations

import copy
import functools
import itertools
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .core import Command, Group, _maybe_await
from .errors import CommandError

__all__ = (
    "Paginator",
    "HelpCommand",
    "DefaultHelpCommand",
    "MinimalHelpCommand",
)


def _string_width(value: str) -> int:
    return len(value)


class Paginator:
    """Build message-sized pages for Fluxer help output."""

    def __init__(
        self,
        prefix: str | None = "```",
        suffix: str | None = "```",
        max_size: int = 2000,
        linesep: str = "\n",
    ) -> None:
        self.prefix = prefix
        self.suffix = suffix
        self.max_size = max_size
        self.linesep = linesep
        self.clear()

    @property
    def _prefix_len(self) -> int:
        return len(self.prefix) if self.prefix else 0

    @property
    def _suffix_len(self) -> int:
        return len(self.suffix) if self.suffix else 0

    @property
    def _linesep_len(self) -> int:
        return len(self.linesep)

    def clear(self) -> None:
        """Clear every buffered page."""

        if self.prefix is None:
            self._current_page: list[str] = []
            self._count = 0
        else:
            self._current_page = [self.prefix]
            self._count = len(self.prefix) + self._linesep_len
        self._pages: list[str] = []

    def add_line(self, line: str = "", *, empty: bool = False) -> None:
        """Add a line to the current page."""

        max_page_size = (
            self.max_size
            - self._prefix_len
            - self._suffix_len
            - (2 * self._linesep_len)
        )
        if len(line) > max_page_size:
            raise RuntimeError(f"Line exceeds maximum page size {max_page_size}")

        if (
            self._count + len(line) + self._linesep_len
            > self.max_size - self._suffix_len
        ):
            self.close_page()

        self._current_page.append(line)
        self._count += len(line) + self._linesep_len

        if empty:
            self._current_page.append("")
            self._count += self._linesep_len

    def close_page(self) -> None:
        """Finish the current page and start a new one."""

        if self.suffix is not None:
            self._current_page.append(self.suffix)
        self._pages.append(self.linesep.join(self._current_page))

        if self.prefix is None:
            self._current_page = []
            self._count = 0
        else:
            self._current_page = [self.prefix]
            self._count = len(self.prefix) + self._linesep_len

    @property
    def pages(self) -> list[str]:
        """Return the rendered help pages."""

        if len(self._current_page) > (0 if self.prefix is None else 1):
            self.close_page()
        return self._pages

    def __len__(self) -> int:
        return sum(len(page) for page in self._pages) + self._count

    def __repr__(self) -> str:
        return (
            f"<Paginator prefix: {self.prefix!r} suffix: {self.suffix!r} "
            f"linesep: {self.linesep!r} max_size: {self.max_size} count: {self._count}>"
        )


def _not_overridden(func: Callable[..., Any]) -> Callable[..., Any]:
    setattr(func, "__help_command_not_overridden__", True)
    return func


class _HelpCommandImpl(Command):
    def __init__(self, injected: HelpCommand, **attrs: Any) -> None:
        super().__init__(injected.command_callback, **attrs)
        self._original = injected
        self._injected = injected

    async def prepare(self, ctx: Any) -> None:
        injected = self._original.copy()
        injected.context = ctx
        self._injected = injected
        self.callback = injected.command_callback
        if not hasattr(
            injected.on_help_command_error, "__help_command_not_overridden__"
        ):
            self.error_handler = injected.on_help_command_error
        await super().prepare(ctx)

    async def _parse_arguments(self, ctx: Any) -> None:
        original_cog = self.cog
        self.cog = None
        try:
            await super()._parse_arguments(ctx)
        finally:
            self.cog = original_cog

    def _inject_into_cog(self, cog: Any) -> None:
        def wrapped_get_commands(
            *, _original: Callable[[], list[Command]] = cog.get_commands
        ) -> list[Command]:
            return [*_original(), self]

        def wrapped_walk_commands(
            *, _original: Callable[[], Iterable[Command]] = cog.walk_commands
        ) -> list[Command]:
            return [*_original(), self]

        functools.update_wrapper(wrapped_get_commands, cog.get_commands)
        functools.update_wrapper(wrapped_walk_commands, cog.walk_commands)
        cog.get_commands = wrapped_get_commands
        cog.walk_commands = wrapped_walk_commands
        self.cog = cog

    def _eject_cog(self) -> None:
        if self.cog is None:
            return
        cog = self.cog
        if hasattr(cog.get_commands, "__wrapped__"):
            cog.get_commands = cog.get_commands.__wrapped__
        if hasattr(cog.walk_commands, "__wrapped__"):
            cog.walk_commands = cog.walk_commands.__wrapped__
        self.cog = None


class HelpCommand:
    """Base class for Fluxer command help formatters."""

    __original_args__: tuple[Any, ...]
    __original_kwargs__: dict[str, Any]

    MENTION_TRANSFORMS = {
        "@everyone": "@\u200beveryone",
        "@here": "@\u200bhere",
        r"<@!?[0-9]{17,22}>": "@deleted-user",
        r"<@&[0-9]{17,22}>": "@deleted-role",
    }
    MENTION_PATTERN = re.compile("|".join(MENTION_TRANSFORMS))

    def __new__(cls, *args: Any, **kwargs: Any) -> HelpCommand:
        self = super().__new__(cls)
        self.__original_args__ = copy.deepcopy(args)
        self.__original_kwargs__ = {
            key: copy.deepcopy(value) for key, value in kwargs.items()
        }
        return self

    def __init__(self, **options: Any) -> None:
        self.show_hidden = bool(options.pop("show_hidden", False))
        self.verify_checks: bool | None = options.pop("verify_checks", True)
        self.command_attrs: dict[str, Any] = options.pop("command_attrs", {})
        self.command_attrs.setdefault("name", "help")
        self.command_attrs.setdefault("help", "Shows this message.")
        self.context: Any = None
        self._command_impl = _HelpCommandImpl(self, **self.command_attrs)

    def copy(self) -> HelpCommand:
        copied = self.__class__(*self.__original_args__, **self.__original_kwargs__)
        copied._command_impl = self._command_impl
        return copied

    def _add_to_bot(self, bot: Any) -> None:
        command = _HelpCommandImpl(self, **self.command_attrs)
        bot.add_command(command)
        self._command_impl = command

    def _remove_from_bot(self, bot: Any) -> None:
        bot.remove_command(self._command_impl.name)
        self._command_impl._eject_cog()

    def add_check(self, func: Callable[..., Any]) -> None:
        """Add a check to the generated help command."""

        self._command_impl.add_check(func)

    def remove_check(self, func: Callable[..., Any]) -> None:
        """Remove a check from the generated help command."""

        self._command_impl.remove_check(func)

    def get_bot_mapping(self) -> dict[Any, list[Any]]:
        """Return the command mapping passed to ``send_bot_help``."""

        bot = self.context.bot
        mapping = {cog: cog.get_commands() for cog in bot.cogs.values()}
        mapping[None] = [command for command in bot.commands if command.cog is None]
        return mapping

    @property
    def clean_prefix(self) -> str:
        prefix = self.context.prefix or ""
        user = self.context.bot.user
        if user is None:
            return prefix
        display_name = getattr(
            user,
            "display_name",
            getattr(user, "username", str(getattr(user, "id", ""))),
        )
        return re.sub(rf"<@!?{getattr(user, 'id', '')}>", f"@{display_name}", prefix)

    @property
    def invoked_with(self) -> str:
        command_name = self._command_impl.name
        ctx = self.context
        if (
            ctx is None
            or ctx.command is None
            or ctx.command.qualified_name != command_name
        ):
            return command_name
        return ctx.invoked_with or command_name

    @property
    def cog(self) -> Any | None:
        return self._command_impl.cog

    @cog.setter
    def cog(self, cog: Any | None) -> None:
        self._command_impl._eject_cog()
        if cog is not None:
            self._command_impl._inject_into_cog(cog)

    def get_command_signature(self, command: Any) -> str:
        parent = getattr(command, "parent", None)
        entries = []
        while parent is not None:
            if not parent.signature or getattr(parent, "invoke_without_command", False):
                entries.append(parent.name)
            else:
                entries.append(f"{parent.name} {parent.signature}")
            parent = parent.parent
        parent_signature = " ".join(reversed(entries))

        if command.aliases:
            name = f"[{command.name}|{'|'.join(command.aliases)}]"
        else:
            name = command.name
        if parent_signature:
            name = f"{parent_signature} {name}"
        return f"{self.clean_prefix}{name} {command.signature}".strip()

    def remove_mentions(self, string: str) -> str:
        """Replace broad mentions in help errors with inert text."""

        def replace(match: re.Match[str]) -> str:
            value = match.group(0)
            if value in self.MENTION_TRANSFORMS:
                return self.MENTION_TRANSFORMS[value]
            if value.startswith("<@&"):
                return "@deleted-role"
            if value.startswith("<@"):
                return "@deleted-user"
            return "@invalid"

        return self.MENTION_PATTERN.sub(replace, string)

    def command_not_found(self, string: str) -> str:
        return f'No command called "{string}" found.'

    def subcommand_not_found(self, command: Any, string: str) -> str:
        if isinstance(command, Group) and command.all_commands:
            return (
                f'Command "{command.qualified_name}" has no subcommand named {string}'
            )
        return f'Command "{command.qualified_name}" has no subcommands.'

    async def filter_commands(
        self,
        commands: Iterable[Any],
        *,
        sort: bool = False,
        key: Callable[[Any], Any] | None = None,
    ) -> list[Any]:
        key = key or (lambda command: command.name)
        iterator = (
            commands
            if self.show_hidden
            else (command for command in commands if not command.hidden)
        )

        if self.verify_checks is False:
            filtered = list(iterator)
        elif self.verify_checks is None and self.context.guild is None:
            filtered = list(iterator)
        else:
            filtered = []
            for command in iterator:
                try:
                    can_run = await command.can_run(self.context)
                except CommandError:
                    can_run = False
                if can_run:
                    filtered.append(command)

        if sort:
            filtered.sort(key=key)
        return filtered

    def get_max_size(self, commands: Iterable[Any]) -> int:
        return max((_string_width(command.name) for command in commands), default=0)

    def get_destination(self) -> Any:
        """Return the channel-like object that receives help output."""

        return self.context.channel

    async def send_error_message(self, error: str) -> None:
        await self.get_destination().send(error)

    @_not_overridden
    async def on_help_command_error(self, ctx: Any, error: Exception) -> None:
        raise error

    async def send_bot_help(self, mapping: Mapping[Any, list[Any]]) -> None:
        return None

    async def send_cog_help(self, cog: Any) -> None:
        return None

    async def send_group_help(self, group: Group) -> None:
        return None

    async def send_command_help(self, command: Command) -> None:
        return None

    async def prepare_help_command(self, ctx: Any, command: str | None = None) -> None:
        return None

    async def command_callback(self, ctx: Any, *, command: str | None = None) -> None:
        """Route a help request to the relevant Fluxer command help hook."""

        self.context = ctx
        await self.prepare_help_command(ctx, command)
        bot = ctx.bot

        if command is None:
            return await self.send_bot_help(self.get_bot_mapping())

        cog = bot.get_cog(command)
        if cog is not None:
            return await self.send_cog_help(cog)

        keys = command.split()
        cmd = bot.all_commands.get(keys[0])
        if cmd is None:
            error = await _maybe_await(
                self.command_not_found(self.remove_mentions(keys[0]))
            )
            return await self.send_error_message(error)

        for key in keys[1:]:
            if not isinstance(cmd, Group):
                error = await _maybe_await(
                    self.subcommand_not_found(cmd, self.remove_mentions(key))
                )
                return await self.send_error_message(error)
            found = cmd.all_commands.get(key)
            if found is None:
                error = await _maybe_await(
                    self.subcommand_not_found(cmd, self.remove_mentions(key))
                )
                return await self.send_error_message(error)
            cmd = found

        if isinstance(cmd, Group):
            return await self.send_group_help(cmd)
        return await self.send_command_help(cmd)


class DefaultHelpCommand(HelpCommand):
    """Default Fluxer command help formatter."""

    def __init__(self, **options: Any) -> None:
        self.width = int(options.pop("width", 80))
        self.indent = int(options.pop("indent", 2))
        self.sort_commands = bool(options.pop("sort_commands", True))
        self.dm_help: bool | None = options.pop("dm_help", False)
        self.dm_help_threshold = int(options.pop("dm_help_threshold", 1000))
        self.commands_heading = str(options.pop("commands_heading", "Commands:"))
        self.no_category = str(options.pop("no_category", "No Category"))
        self.paginator: Paginator = options.pop("paginator", None) or Paginator()
        super().__init__(**options)

    def shorten_text(self, text: str) -> str:
        return text[: self.width - 3] + "..." if len(text) > self.width else text

    def get_ending_note(self) -> str:
        return (
            f"Type {self.clean_prefix}{self.invoked_with} command for more info on a command.\n"
            f"You can also type {self.clean_prefix}{self.invoked_with} category for more info on a category."
        )

    def add_indented_commands(
        self, commands: list[Any], *, heading: str, max_size: int | None = None
    ) -> None:
        if not commands:
            return
        self.paginator.add_line(heading)
        max_size = max_size or self.get_max_size(commands)
        for command in commands:
            width = max_size - (_string_width(command.name) - len(command.name))
            entry = f"{self.indent * ' '}{command.name:<{width}} {command.short_doc}"
            self.paginator.add_line(self.shorten_text(entry))

    async def send_pages(self) -> None:
        destination = self.get_destination()
        for page in self.paginator.pages:
            await destination.send(page)

    def add_command_formatting(self, command: Any) -> None:
        if command.description:
            self.paginator.add_line(command.description, empty=True)
        self.paginator.add_line(self.get_command_signature(command), empty=True)
        if command.help:
            try:
                self.paginator.add_line(command.help, empty=True)
            except RuntimeError:
                for line in command.help.splitlines():
                    self.paginator.add_line(line)
                self.paginator.add_line()

    def get_destination(self) -> Any:
        ctx = self.context
        author_can_receive = hasattr(ctx.author, "send")
        if self.dm_help is True and author_can_receive:
            return ctx.author
        if (
            self.dm_help is None
            and len(self.paginator) > self.dm_help_threshold
            and author_can_receive
        ):
            return ctx.author
        return ctx.channel

    async def prepare_help_command(self, ctx: Any, command: str | None = None) -> None:
        self.paginator.clear()
        await super().prepare_help_command(ctx, command)

    async def send_bot_help(self, mapping: Mapping[Any, list[Any]]) -> None:
        bot = self.context.bot
        if bot.description:
            self.paginator.add_line(bot.description, empty=True)

        no_category = f"\u200b{self.no_category}:"

        def get_category(command: Any) -> str:
            cog = command.cog
            return f"{cog.qualified_name}:" if cog is not None else no_category

        filtered = await self.filter_commands(bot.commands, sort=True, key=get_category)
        max_size = self.get_max_size(filtered)
        for category, commands in itertools.groupby(filtered, key=get_category):
            command_list = (
                sorted(commands, key=lambda command: command.name)
                if self.sort_commands
                else list(commands)
            )
            self.add_indented_commands(
                command_list, heading=category, max_size=max_size
            )

        note = self.get_ending_note()
        if note:
            self.paginator.add_line()
            self.paginator.add_line(note)
        await self.send_pages()

    async def send_command_help(self, command: Command) -> None:
        self.add_command_formatting(command)
        self.paginator.close_page()
        await self.send_pages()

    async def send_group_help(self, group: Group) -> None:
        self.add_command_formatting(group)
        filtered = await self.filter_commands(group.commands, sort=self.sort_commands)
        self.add_indented_commands(filtered, heading=self.commands_heading)
        if filtered:
            note = self.get_ending_note()
            if note:
                self.paginator.add_line()
                self.paginator.add_line(note)
        await self.send_pages()

    async def send_cog_help(self, cog: Any) -> None:
        if cog.description:
            self.paginator.add_line(cog.description, empty=True)
        filtered = await self.filter_commands(
            cog.get_commands(), sort=self.sort_commands
        )
        self.add_indented_commands(filtered, heading=self.commands_heading)
        note = self.get_ending_note()
        if note:
            self.paginator.add_line()
            self.paginator.add_line(note)
        await self.send_pages()


class MinimalHelpCommand(HelpCommand):
    """Compact Fluxer command help formatter."""

    def __init__(self, **options: Any) -> None:
        self.sort_commands = bool(options.pop("sort_commands", True))
        self.commands_heading = str(options.pop("commands_heading", "Commands"))
        self.aliases_heading = str(options.pop("aliases_heading", "Aliases:"))
        self.dm_help: bool | None = options.pop("dm_help", False)
        self.dm_help_threshold = int(options.pop("dm_help_threshold", 1000))
        self.no_category = str(options.pop("no_category", "No Category"))
        self.paginator: Paginator = options.pop("paginator", None) or Paginator(
            prefix=None, suffix=None
        )
        super().__init__(**options)

    async def send_pages(self) -> None:
        destination = self.get_destination()
        for page in self.paginator.pages:
            await destination.send(page)

    def get_opening_note(self) -> str:
        return (
            f"Use `{self.clean_prefix}{self.invoked_with} [command]` for more info on a command.\n"
            f"You can also use `{self.clean_prefix}{self.invoked_with} [category]` for more info on a category."
        )

    def get_command_signature(self, command: Any) -> str:
        return (
            f"{self.clean_prefix}{command.qualified_name} {command.signature}".strip()
        )

    def get_ending_note(self) -> str | None:
        return None

    def add_bot_commands_formatting(self, commands: list[Any], heading: str) -> None:
        if commands:
            self.paginator.add_line(f"__**{heading}**__")
            self.paginator.add_line("\u2002".join(command.name for command in commands))

    def add_subcommand_formatting(self, command: Any) -> None:
        if command.short_doc:
            self.paginator.add_line(
                f"{self.clean_prefix}{command.qualified_name} \N{EN DASH} {command.short_doc}"
            )
        else:
            self.paginator.add_line(f"{self.clean_prefix}{command.qualified_name}")

    def add_aliases_formatting(self, aliases: list[str]) -> None:
        self.paginator.add_line(
            f"**{self.aliases_heading}** {', '.join(aliases)}", empty=True
        )

    def add_command_formatting(self, command: Any) -> None:
        if command.description:
            self.paginator.add_line(command.description, empty=True)
        if command.aliases:
            self.paginator.add_line(self.get_command_signature(command))
            self.add_aliases_formatting(command.aliases)
        else:
            self.paginator.add_line(self.get_command_signature(command), empty=True)
        if command.help:
            try:
                self.paginator.add_line(command.help, empty=True)
            except RuntimeError:
                for line in command.help.splitlines():
                    self.paginator.add_line(line)
                self.paginator.add_line()

    def get_destination(self) -> Any:
        ctx = self.context
        author_can_receive = hasattr(ctx.author, "send")
        if self.dm_help is True and author_can_receive:
            return ctx.author
        if (
            self.dm_help is None
            and len(self.paginator) > self.dm_help_threshold
            and author_can_receive
        ):
            return ctx.author
        return ctx.channel

    async def prepare_help_command(self, ctx: Any, command: str | None = None) -> None:
        self.paginator.clear()
        await super().prepare_help_command(ctx, command)

    async def send_bot_help(self, mapping: Mapping[Any, list[Any]]) -> None:
        bot = self.context.bot
        if bot.description:
            self.paginator.add_line(bot.description, empty=True)
        opening = self.get_opening_note()
        if opening:
            self.paginator.add_line(opening, empty=True)

        no_category = f"\u200b{self.no_category}"

        def get_category(command: Any) -> str:
            cog = command.cog
            return cog.qualified_name if cog is not None else no_category

        filtered = await self.filter_commands(bot.commands, sort=True, key=get_category)
        for category, commands in itertools.groupby(filtered, key=get_category):
            command_list = (
                sorted(commands, key=lambda command: command.name)
                if self.sort_commands
                else list(commands)
            )
            self.add_bot_commands_formatting(command_list, category)

        ending = self.get_ending_note()
        if ending:
            self.paginator.add_line()
            self.paginator.add_line(ending)
        await self.send_pages()

    async def send_cog_help(self, cog: Any) -> None:
        bot = self.context.bot
        if bot.description:
            self.paginator.add_line(bot.description, empty=True)
        opening = self.get_opening_note()
        if opening:
            self.paginator.add_line(opening, empty=True)
        if cog.description:
            self.paginator.add_line(cog.description, empty=True)

        filtered = await self.filter_commands(
            cog.get_commands(), sort=self.sort_commands
        )
        if filtered:
            self.paginator.add_line(f"**{cog.qualified_name} {self.commands_heading}**")
            for command in filtered:
                self.add_subcommand_formatting(command)

        ending = self.get_ending_note()
        if ending:
            self.paginator.add_line()
            self.paginator.add_line(ending)
        await self.send_pages()

    async def send_group_help(self, group: Group) -> None:
        self.add_command_formatting(group)
        filtered = await self.filter_commands(group.commands, sort=self.sort_commands)
        if filtered:
            opening = self.get_opening_note()
            if opening:
                self.paginator.add_line(opening, empty=True)
            self.paginator.add_line(f"**{self.commands_heading}**")
            for command in filtered:
                self.add_subcommand_formatting(command)

        ending = self.get_ending_note()
        if ending:
            self.paginator.add_line()
            self.paginator.add_line(ending)
        await self.send_pages()

    async def send_command_help(self, command: Command) -> None:
        self.add_command_formatting(command)
        await self.send_pages()
