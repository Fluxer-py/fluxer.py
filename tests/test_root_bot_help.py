"""Root bot help, shared event handling, and root check compatibility."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import fluxer
from fluxer.ext import commands
from fluxer.ext.commands import core


class Message:
    """Minimal message used by command and event tests."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.author = SimpleNamespace(id=1, bot=False)
        self.guild = None
        self.guild_id = None
        self.channel = SimpleNamespace(send=AsyncMock())
        self.reply = AsyncMock()


def test_root_exports_and_default_help() -> None:
    assert fluxer.Bot is commands.Bot
    assert fluxer.Cog is commands.Cog
    assert fluxer.when_mentioned is commands.when_mentioned
    assert fluxer.when_mentioned_or is commands.when_mentioned_or
    assert fluxer.Bot(command_prefix="!").get_command("help") is not None
    assert fluxer.Bot(command_prefix="!", help_command=None).get_command("help") is None
    with pytest.raises(TypeError):
        fluxer.Bot()  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_root_help_supports_commands_groups_and_aliases() -> None:
    bot = fluxer.Bot(command_prefix="!")

    @bot.command(aliases=["hi"])
    async def greet(ctx: commands.Context) -> None:
        """Greet someone."""

    @bot.group()
    async def tools(ctx: commands.Context) -> None:
        """Utility commands."""

    @tools.command(aliases=["show"])
    async def list_items(ctx: commands.Context) -> None:
        """List items."""

    for invocation, expected in (
        ("!help", "greet"),
        ("!help greet", "Greet someone"),
        ("!help hi", "Greet someone"),
        ("!help tools", "list_items"),
        ("!help tools show", "List items"),
    ):
        message = Message(invocation)
        await bot.invoke(await bot.get_context(message))
        output = "\n".join(call.args[0] for call in message.channel.send.call_args_list)
        assert expected in output

    custom = commands.MinimalHelpCommand()
    bot.help_command = custom
    assert bot.help_command is custom
    bot.help_command = None
    assert bot.get_command("help") is None


@pytest.mark.asyncio
async def test_client_and_bot_share_one_listener_registry() -> None:
    bot = fluxer.Bot(command_prefix="!", help_command=None)
    calls: list[str] = []

    @bot.event
    async def on_message(message: Message) -> None:
        calls.append("event")

    @bot.listen("on_message")
    async def extra(message: Message) -> None:
        calls.append("listener")

    class ListenerCog(fluxer.Cog):
        @fluxer.Cog.listener("on_message")
        async def observe(self, message: Message) -> None:
            calls.append("cog")

    await bot.add_cog(ListenerCog(bot))
    bot.dispatch("on_message", Message("manual"))
    await asyncio.sleep(0)
    assert calls == ["event", "listener", "cog"]

    bot.remove_listener(extra, "on_message")
    await bot.remove_cog("ListenerCog")
    await bot._fire("on_message", Message("gateway"))
    assert calls == ["event", "listener", "cog", "event"]

    await bot.close()


@pytest.mark.asyncio
async def test_client_listener_api_uses_the_same_event_path() -> None:
    client = fluxer.Client()
    seen: list[str] = []

    @client.on("ready")
    async def ready() -> None:
        seen.append("ready")

    @client.listen("on_ready")
    async def extra() -> None:
        seen.append("extra")

    await client._fire("on_ready")
    assert seen == ["ready", "extra"]
    client.remove_listener(extra, "on_ready")
    client.dispatch("on_ready")
    await asyncio.sleep(0)
    assert seen == ["ready", "extra", "ready"]
    await client.close()


@pytest.mark.asyncio
async def test_gateway_message_fires_listener_and_processes_command() -> None:
    bot = fluxer.Bot(command_prefix="!", help_command=None)
    message = Message("!ping")
    bot._parse_message = lambda data: message  # type: ignore[method-assign]
    seen: list[str] = []

    @bot.listen("on_message")
    async def observe(received: Message) -> None:
        seen.append("event")

    @bot.command()
    async def ping(ctx: commands.Context) -> None:
        seen.append("command")

    await bot._dispatch("MESSAGE_CREATE", {})
    await asyncio.sleep(0)
    assert seen == ["event", "command"]
    await bot.close()


@pytest.mark.asyncio
async def test_root_checks_attach_framework_predicates(monkeypatch: pytest.MonkeyPatch) -> None:
    role_check = AsyncMock(return_value=True)
    permission_check = AsyncMock(return_value=True)
    monkeypatch.setattr(core, "_member_has_role", role_check)
    monkeypatch.setattr(core, "_check_fluxer_permissions", permission_check)

    @commands.command()
    @fluxer.has_role(id="42")
    async def role_command(ctx: commands.Context) -> None:
        pass

    @commands.command()
    @fluxer.has_permission(
        fluxer.Permissions.KICK_MEMBERS | fluxer.Permissions.BAN_MEMBERS
    )
    async def permission_command(ctx: commands.Context) -> None:
        pass

    @commands.command()
    @fluxer.has_role(name="Mods")
    async def named_role_command(ctx: commands.Context) -> None:
        pass

    ctx = SimpleNamespace(author=SimpleNamespace(id=7))
    assert await role_command.checks[0](ctx)
    role_check.assert_awaited_once_with(ctx, 7, (42,))
    assert await named_role_command.checks[0](ctx)
    role_check.assert_awaited_with(ctx, 7, ("Mods",))
    assert await permission_command.checks[0](ctx)
    permission_check.assert_awaited_once_with(
        ctx, 7, {"kick_members": True, "ban_members": True}
    )

    with pytest.raises(ValueError):
        fluxer.has_role()
    with pytest.raises(ValueError):
        fluxer.has_role(name="Mods", id=42)
    with pytest.raises(ValueError):
        fluxer.has_permission(fluxer.Permissions(1 << 63))
