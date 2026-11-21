"""Local, cog and global command error handlers."""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from fluxer.ext import commands


class Message:
    """Minimal message for invoking commands offline."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.author = SimpleNamespace(id=1, bot=False)
        self.guild = None
        self.guild_id = None
        self.channel = SimpleNamespace(send=AsyncMock())


async def run(bot: commands.Bot, content: str) -> commands.Context:
    ctx = await bot.get_context(Message(content))  # type: ignore[arg-type]
    await bot.invoke(ctx)
    for _ in range(3):
        await asyncio.sleep(0)
    return ctx


def error_recorder(bot: commands.Bot) -> list[tuple[str, Any]]:
    seen: list[tuple[str, Any]] = []

    @bot.listen("on_command_error")
    async def on_command_error(ctx: commands.Context, error: Exception) -> None:
        seen.append(("global", error))

    return seen


@pytest.mark.asyncio
async def test_local_handler_then_global_with_wrapped_errors() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None)
    seen = error_recorder(bot)

    @bot.command()
    async def boom(ctx: commands.Context, amount: int) -> None:
        raise ValueError("nope")

    @boom.error
    async def boom_error(ctx: commands.Context, error: Exception) -> None:
        seen.append(("local", error))

    assert boom.has_error_handler() and hasattr(boom, "on_error")
    assert boom.error_handler is boom_error

    ctx = await run(bot, "!boom 3")
    assert [where for where, _ in seen] == ["local", "global"]
    local = seen[0][1]
    assert isinstance(local, commands.CommandInvokeError)
    assert isinstance(local.original, ValueError) and seen[1][1] is local
    assert ctx.command_failed

    seen.clear()
    await run(bot, "!boom")
    assert isinstance(seen[0][1], commands.MissingRequiredArgument)
    seen.clear()
    await run(bot, "!boom notanumber")
    assert isinstance(seen[0][1], commands.BadArgument)
    assert not isinstance(seen[0][1], commands.CommandInvokeError)
    await bot.close()


@pytest.mark.asyncio
async def test_default_logging_is_skipped_when_a_local_handler_exists(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = commands.Bot(command_prefix="!", help_command=None)
    handled: list[Exception] = []

    @bot.command()
    async def quiet(ctx: commands.Context) -> None:
        raise ValueError("handled")

    @quiet.error
    async def quiet_error(ctx: commands.Context, error: Exception) -> None:
        handled.append(error)

    @bot.command()
    async def loud(ctx: commands.Context) -> None:
        raise ValueError("unhandled")

    with caplog.at_level(logging.ERROR):
        await run(bot, "!quiet")
    assert handled and "Ignoring exception in command" not in caplog.text
    with caplog.at_level(logging.ERROR):
        await run(bot, "!loud")
    assert "Ignoring exception in command" in caplog.text
    await bot.close()


def test_error_rejects_plain_functions_and_handlers_can_be_removed() -> None:
    @commands.command()
    async def cmd(ctx: commands.Context) -> None:
        pass

    assert not cmd.has_error_handler() and cmd.error_handler is None
    with pytest.raises(TypeError):
        cmd.error(lambda ctx, error: None)  # type: ignore[arg-type, return-value]

    async def handler(ctx: commands.Context, error: Exception) -> None:
        pass

    cmd.error(handler)
    copied = cmd.copy()
    assert copied.error_handler is handler
    cmd.error_handler = None
    assert not cmd.has_error_handler() and not hasattr(cmd, "on_error")


@pytest.mark.asyncio
async def test_cog_local_handler_cog_handler_and_ctx_cog() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None)
    seen = error_recorder(bot)

    class Tools(commands.Cog):
        @commands.command()
        async def fail(self, ctx: commands.Context) -> None:
            raise ValueError("cog")

        @fail.error
        async def fail_error(self, ctx: commands.Context, error: Exception) -> None:
            seen.append(("local", (self, ctx.cog)))

        async def cog_command_error(self, ctx: Any, error: Exception) -> None:
            seen.append(("cog", self))

    cog = Tools(bot)
    await bot.add_cog(cog)
    assert cog.has_error_handler() and not commands.Cog(bot).has_error_handler()
    await run(bot, "!fail")
    assert [where for where, _ in seen] == ["local", "cog", "global"]
    assert seen[0][1] == (cog, cog) and seen[1][1] is cog
    await bot.close()


@pytest.mark.asyncio
async def test_group_subcommand_handler() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None)
    seen = error_recorder(bot)

    @bot.group()
    async def tools(ctx: commands.Context) -> None:
        pass

    @tools.command()
    async def run_it(ctx: commands.Context) -> None:
        raise ValueError("sub")

    @run_it.error
    async def run_error(ctx: commands.Context, error: Exception) -> None:
        seen.append(("local", ctx.command))

    await run(bot, "!tools run_it")
    assert seen[0] == ("local", run_it) and seen[1][0] == "global"
    await bot.close()


@pytest.mark.asyncio
async def test_global_checks_raise_check_failure_to_handlers() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None)
    seen = error_recorder(bot)
    ran: list[str] = []

    @bot.command()
    async def guarded(ctx: commands.Context) -> None:
        ran.append("guarded")

    bot.add_check(lambda ctx: False)
    await run(bot, "!guarded")
    assert not ran and isinstance(seen[0][1], commands.CheckFailure)

    bot = commands.Bot(command_prefix="!", help_command=None)
    seen = error_recorder(bot)
    bot.add_check(lambda ctx: False, call_once=True)

    @bot.command()
    async def once(ctx: commands.Context) -> None:
        ran.append("once")

    await run(bot, "!once")
    assert not ran and isinstance(seen[0][1], commands.CheckFailure)
    await bot.close()
