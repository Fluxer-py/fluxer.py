"""Command name registration and case lookup regressions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from fluxer.ext import commands


class Message:
    """Minimal message for command lookup and invocation."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.author = type("Author", (), {"bot": False})()
        self.channel = type("Channel", (), {})()


@pytest.mark.parametrize("insensitive", [False, True])
@pytest.mark.asyncio
async def test_callback_and_explicit_name_collision(insensitive: bool) -> None:
    bot = commands.Bot(
        command_prefix="!", help_command=None, case_insensitive=insensitive
    )

    @bot.command()
    async def launch(ctx: commands.Context) -> None:
        pass

    original = bot.get_command("launch")
    with pytest.raises(commands.CommandRegistrationError) as caught:

        @bot.command(name="launch")
        async def another(ctx: commands.Context) -> None:
            pass

    message = str(caught.value)
    assert "launch" in message
    assert "another" in message
    assert "test_command_registration.py:" in message
    assert bot.get_command("launch") is original


@pytest.mark.parametrize("insensitive", [False, True])
@pytest.mark.asyncio
async def test_case_rule_matches_lookup_and_registration(insensitive: bool) -> None:
    bot = commands.Bot(
        command_prefix="!", help_command=None, case_insensitive=insensitive
    )

    @bot.command(name="tHIs")
    async def first(ctx: commands.Context) -> None:
        pass

    if insensitive:
        with pytest.raises(commands.CommandRegistrationError):

            @bot.command(name="this")
            async def second(ctx: commands.Context) -> None:
                pass

        assert bot.get_command("THIS") is first
        assert (await bot.get_context(Message("!THIS"))).command is first
    else:

        @bot.command(name="this")
        async def second(ctx: commands.Context) -> None:
            pass

        assert bot.get_command("THIS") is None
        assert bot.get_command("tHIs") is first
        assert bot.get_command("this") is second


@pytest.mark.asyncio
async def test_alias_collisions_and_failed_registration_preserve_registry() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None, case_insensitive=True)

    @bot.command(name="alpha", aliases=["shortcut"])
    async def first(ctx: commands.Context) -> None:
        pass

    with pytest.raises(commands.CommandRegistrationError, match="SHORTCUT"):

        @bot.command(name="beta", aliases=["other", "SHORTCUT"])
        async def second(ctx: commands.Context) -> None:
            pass

    assert bot.get_command("alpha") is first
    assert bot.get_command("shortcut") is first
    assert bot.get_command("beta") is None
    assert bot.get_command("other") is None

    with pytest.raises(commands.CommandRegistrationError, match="SAME"):

        @bot.command(name="same", aliases=["SAME"])
        async def internal(ctx: commands.Context) -> None:
            pass


@pytest.mark.asyncio
async def test_group_sibling_collision_and_distinct_group_namespaces() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None, case_insensitive=True)

    @bot.group(name="first")
    async def first_group(ctx: commands.Context) -> None:
        pass

    @first_group.command(name="Item")
    async def first_item(ctx: commands.Context) -> None:
        pass

    with pytest.raises(commands.CommandRegistrationError, match="first"):

        @first_group.command(name="item")
        async def duplicate(ctx: commands.Context) -> None:
            pass

    @bot.group(name="second")
    async def second_group(ctx: commands.Context) -> None:
        pass

    @second_group.command(name="item")
    async def second_item(ctx: commands.Context) -> None:
        pass

    assert bot.get_command("FIRST ITEM") is first_item
    assert bot.get_command("SECOND ITEM") is second_item
    assert (await bot.get_context(Message("!FIRST"))).command is first_group


@pytest.mark.asyncio
async def test_cog_case_collision_is_detected_before_insertion() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None, case_insensitive=True)

    @bot.command(name="shared")
    async def existing(ctx: commands.Context) -> None:
        pass

    class Tools(commands.Cog):
        @commands.command(name="unique")
        async def unique(self, ctx: commands.Context) -> None:
            pass

        @commands.command(name="SHARED")
        async def conflict(self, ctx: commands.Context) -> None:
            pass

    with pytest.raises(commands.CommandRegistrationError, match="SHARED"):
        await bot.add_cog(Tools(bot))
    assert bot.get_command("shared") is existing
    assert bot.get_command("unique") is None
    assert bot.get_cog("Tools") is None


@pytest.mark.asyncio
async def test_predeclared_group_is_checked_when_added_to_insensitive_bot() -> None:
    @commands.group(name="tools")
    async def tools(ctx: commands.Context) -> None:
        pass

    @tools.command(name="Info")
    async def info(ctx: commands.Context) -> None:
        pass

    @tools.command(name="info")
    async def other(ctx: commands.Context) -> None:
        pass

    bot = commands.Bot(command_prefix="!", help_command=None, case_insensitive=True)
    with pytest.raises(commands.CommandRegistrationError, match="info"):
        bot.add_command(tools)
    assert bot.get_command("tools") is None


@pytest.mark.asyncio
async def test_predeclared_group_keeps_distinct_case_in_sensitive_bot() -> None:
    @commands.group(name="tools")
    async def tools(ctx: commands.Context) -> None:
        pass

    @tools.command(name="Info")
    async def upper(ctx: commands.Context) -> None:
        pass

    @tools.command(name="info")
    async def lower(ctx: commands.Context) -> None:
        pass

    bot = commands.Bot(command_prefix="!", help_command=None, case_insensitive=False)
    bot.add_command(tools)
    assert bot.get_command("tools Info") is upper
    assert bot.get_command("tools info") is lower


def test_switching_case_rule_validates_before_reindexing() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None)

    @bot.command(name="Info")
    async def upper(ctx: commands.Context) -> None:
        pass

    @bot.command(name="info")
    async def lower(ctx: commands.Context) -> None:
        pass

    with pytest.raises(commands.CommandRegistrationError, match="info"):
        bot.case_insensitive = True
    assert bot.case_insensitive is False
    assert bot.get_command("Info") is upper
    assert bot.get_command("info") is lower


@pytest.mark.asyncio
async def test_extension_collision_reports_registration_error_as_cause() -> None:
    bot = commands.Bot(command_prefix="!", help_command=None)

    @bot.command(name="shared")
    async def original(ctx: commands.Context) -> None:
        pass

    async def setup(loaded_bot: commands.Bot) -> None:
        @loaded_bot.command(name="shared")
        async def duplicate(ctx: commands.Context) -> None:
            pass

    with patch(
        "fluxer.ext.commands.bot.importlib.import_module",
        return_value=SimpleNamespace(setup=setup),
    ):
        with pytest.raises(commands.ExtensionFailed) as caught:
            await bot.load_extension("example.commands")
    assert isinstance(caught.value.__cause__, commands.CommandRegistrationError)
    assert "shared" in str(caught.value.__cause__)
    assert bot.get_command("shared") is original
    assert bot.extensions == {}


@pytest.mark.asyncio
async def test_duplicate_in_setup_hook_prevents_gateway_connection() -> None:
    class DuplicateBot(commands.Bot):
        async def setup_hook(self) -> None:
            @self.command(name="once")
            async def first(ctx: commands.Context) -> None:
                pass

            @self.command(name="ONCE")
            async def second(ctx: commands.Context) -> None:
                pass

    bot = DuplicateBot(command_prefix="!", help_command=None, case_insensitive=True)
    with (
        patch("fluxer.client.HTTPClient") as http_type,
        patch("fluxer.client.Gateway") as gateway_type,
    ):
        http_type.return_value._ensure_session = AsyncMock()
        http_type.return_value.close = AsyncMock()
        gateway_type.return_value.close = AsyncMock()
        gateway_type.return_value.connect = AsyncMock()
        with pytest.raises(commands.CommandRegistrationError, match="ONCE"):
            await bot.start("test-token")
        gateway_type.return_value.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_case_insensitive_group_invocation_and_help_lookup() -> None:
    bot = commands.Bot(command_prefix="!", case_insensitive=True)
    seen: list[str] = []

    @bot.group(name="Tools")
    async def tools(ctx: commands.Context) -> None:
        pass

    @tools.command(name="Run")
    async def run(ctx: commands.Context) -> None:
        seen.append("run")

    context = await bot.get_context(Message("!TOOLS RUN"))
    await bot.invoke(context)
    assert seen == ["run"]
    assert bot.get_command("tools run") is run
