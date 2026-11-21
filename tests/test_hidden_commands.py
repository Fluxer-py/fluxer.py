"""Hidden commands stay out of help listings unless show_hidden is set."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fluxer.ext import commands


class Message:
    """Minimal message for invoking help offline."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.author = SimpleNamespace(id=1, bot=False)
        self.guild = None
        self.guild_id = None
        self.channel = SimpleNamespace(send=AsyncMock())
        self.reply = AsyncMock()


async def help_text(bot: commands.Bot, query: str) -> str:
    message = Message(query)
    await bot.invoke(await bot.get_context(message))  # type: ignore[arg-type]
    calls = message.channel.send.call_args_list + message.reply.call_args_list
    return "\n".join(str(call.args[0]) for call in calls if call.args)


def make_bot(help_command: commands.HelpCommand) -> commands.Bot:
    bot = commands.Bot(command_prefix="!", help_command=help_command)

    @bot.command()
    async def visible(ctx: commands.Context) -> None:
        """Visible command."""

    @bot.command(hidden=True)
    async def secret(ctx: commands.Context) -> None:
        """Secret command."""

    @bot.group(hidden=True)
    async def admin(ctx: commands.Context) -> None:
        """Hidden group."""

    @bot.group()
    async def tools(ctx: commands.Context) -> None:
        """Tools."""

    @tools.command(hidden=True)
    async def wipe(ctx: commands.Context) -> None:
        """Hidden subcommand."""

    @tools.command()
    async def ping(ctx: commands.Context) -> None:
        """Visible subcommand."""

    return bot


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "help_class", [commands.DefaultHelpCommand, commands.MinimalHelpCommand]
)
async def test_hidden_commands_are_left_out_of_listings(
    help_class: type[commands.HelpCommand],
) -> None:
    bot = make_bot(help_class())
    listing = await help_text(bot, "!help")
    assert "visible" in listing and "tools" in listing
    assert "secret" not in listing and "admin" not in listing
    group = await help_text(bot, "!help tools")
    assert "ping" in group and "wipe" not in group
    # Asking for a hidden command by name still shows its help, as in discord.py.
    assert "Secret command." in await help_text(bot, "!help secret")
    await bot.close()


@pytest.mark.asyncio
async def test_show_hidden_lists_everything() -> None:
    bot = make_bot(commands.DefaultHelpCommand(show_hidden=True))
    listing = await help_text(bot, "!help")
    assert "secret" in listing and "admin" in listing
    assert "wipe" in await help_text(bot, "!help tools")
    await bot.close()


@pytest.mark.asyncio
async def test_help_command_itself_can_be_hidden() -> None:
    bot = make_bot(commands.DefaultHelpCommand(command_attrs={"hidden": True}))
    listing = await help_text(bot, "!help")
    assert "Shows this message" not in listing and "visible" in listing
    await bot.close()


@pytest.mark.asyncio
async def test_cog_command_attrs_hide_its_commands() -> None:
    bot = commands.Bot(command_prefix="!", help_command=commands.DefaultHelpCommand())

    class Admin(commands.Cog, command_attrs=dict(hidden=True)):
        @commands.command()
        async def ban_all(self, ctx: commands.Context) -> None:
            """Hidden by the cog."""

        @commands.command(hidden=False)
        async def status(self, ctx: commands.Context) -> None:
            """Explicitly visible."""

        @commands.group()
        async def config(self, ctx: commands.Context) -> None:
            """Hidden group."""

        @config.command()
        async def reset(self, ctx: commands.Context) -> None:
            """Hidden subcommand."""

    class Plain(commands.Cog):
        @commands.command()
        async def hello(self, ctx: commands.Context) -> None:
            """Plain command."""

    await bot.add_cog(Admin(bot))
    await bot.add_cog(Plain(bot))
    assert Admin.__cog_settings__ == {"hidden": True}  # type: ignore[attr-defined]

    def is_hidden(name: str) -> bool:
        command = bot.get_command(name)
        assert command is not None, name
        return command.hidden

    hidden = {name: is_hidden(name) for name in ("ban_all", "status", "config")}
    assert hidden == {"ban_all": True, "status": False, "config": True}
    assert is_hidden("config reset") and not is_hidden("hello")
    # The class-level command is untouched; only the cog's bound copy changes.
    assert not Admin.ban_all.hidden

    listing = await help_text(bot, "!help")
    assert "status" in listing and "hello" in listing
    assert "ban_all" not in listing and "config" not in listing
    await bot.close()


def test_cog_description_uses_only_its_own_docstring() -> None:
    class Documented(commands.Cog):
        """Moderation tools."""

    class Undocumented(commands.Cog):
        pass

    bot = commands.Bot(command_prefix="!")
    assert Documented(bot).description == "Moderation tools."
    assert Undocumented(bot).description == ""
