"""Command events: on_command, on_command_completion and on_command_error."""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from fluxer.ext import commands


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content
        self.author = SimpleNamespace(id=1, bot=False)
        self.guild = None
        self.guild_id = None
        self.channel = SimpleNamespace(send=AsyncMock())


@pytest.mark.asyncio
async def test_command_completion_and_error_events(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = commands.Bot(command_prefix="!", help_command=None)
    seen: list[tuple[str, Any]] = []

    @bot.command()
    async def ok(ctx: commands.Context) -> None:
        pass

    @bot.command()
    async def fail(ctx: commands.Context) -> None:
        raise ValueError("nope")

    @bot.command()
    async def handled(ctx: commands.Context) -> None:
        raise ValueError("local")

    @handled.error
    async def handled_error(ctx: commands.Context, error: Exception) -> None:
        seen.append(("local", type(error).__name__))

    @bot.listen("on_command")
    async def on_command(ctx: commands.Context) -> None:
        seen.append(("command", getattr(ctx.command, "name", None)))

    @bot.listen("on_command_completion")
    async def on_command_completion(ctx: commands.Context) -> None:
        seen.append(("completion", getattr(ctx.command, "name", None)))

    async def run(content: str) -> None:
        await bot.invoke(await bot.get_context(_Message(content)))
        for _ in range(3):
            await asyncio.sleep(0)

    await run("!ok")
    assert seen == [("command", "ok"), ("completion", "ok")]

    seen.clear()
    with caplog.at_level(logging.ERROR):
        await run("!fail")
    assert seen == [("command", "fail")]
    assert "Ignoring exception in command" in caplog.text

    @bot.event
    async def on_command_error(ctx: commands.Context, error: Exception) -> None:
        seen.append(("error", type(error).__name__))

    seen.clear()
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        await run("!fail")
        await run("!missing")
    assert seen == [
        ("command", "fail"),
        ("error", "CommandInvokeError"),
        ("error", "CommandNotFound"),
    ]
    assert "Ignoring exception in command" not in caplog.text

    # As in discord.py, a local handler runs first and on_command_error still
    # fires afterwards as the catch-all; both receive the wrapped error.
    seen.clear()
    await run("!handled")
    assert sorted(seen) == [
        ("command", "handled"),
        ("error", "CommandInvokeError"),
        ("local", "CommandInvokeError"),
    ]
    await bot.close()
