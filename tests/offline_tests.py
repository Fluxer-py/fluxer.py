from __future__ import annotations

import asyncio
import types
import sys
from pathlib import Path
from typing import Any, Literal, cast


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PACKAGE_ROOT.parent
for path in (str(PACKAGE_ROOT), str(WORKSPACE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _install_import_stubs() -> None:
    if "aiohttp" not in sys.modules:
        aiohttp: Any = types.ModuleType("aiohttp")
        aiohttp.ClientError = RuntimeError
        aiohttp.ClientSession = object
        aiohttp.ClientWebSocketResponse = object
        aiohttp.FormData = object
        aiohttp.WSMsgType = types.SimpleNamespace(
            TEXT=1, BINARY=2, CLOSED=3, CLOSING=4, ERROR=5
        )
        aiohttp.WSServerHandshakeError = RuntimeError
        sys.modules["aiohttp"] = aiohttp
    if "emoji" not in sys.modules:
        emoji: Any = types.ModuleType("emoji")
        emoji.emojize = lambda value, language=None: value
        emoji.demojize = lambda value, language=None: value
        sys.modules["emoji"] = emoji


_install_import_stubs()

import fluxer  # noqa: E402
import fluxer.abc  # noqa: E402
import fluxer.account  # noqa: E402
import fluxer.activity  # noqa: E402
import fluxer.appinfo  # noqa: E402
import fluxer.calls  # noqa: E402
import fluxer.channel  # noqa: E402
import fluxer.emoji  # noqa: E402
import fluxer.flags  # noqa: E402
import fluxer.guild  # noqa: E402
import fluxer.member  # noqa: E402
import fluxer.message  # noqa: E402
import fluxer.partial_emoji  # noqa: E402
import fluxer.permissions  # noqa: E402
import fluxer.reaction  # noqa: E402
import fluxer.role  # noqa: E402
import fluxer.shard  # noqa: E402
import fluxer.user  # noqa: E402
import fluxer.webhook  # noqa: E402
from fluxer.ext import commands  # noqa: E402
from fluxer.gateway import Gateway  # noqa: E402
from fluxer.fluxer_models import (  # noqa: E402
    AppInfo,
    AuthSession,
    AttachmentUpload,
    AttachmentUploadPlan,
    AttachmentUploadSpec,
    AuthorizedIP,
    BanEntry,
    BulkOperationResult,
    BulkEmojiResult,
    BulkStickerResult,
    CallEligibility,
    CallState,
    CompletedAttachmentUploadList,
    DataHarvest,
    DiscoveryApplication,
    DiscoveryGuild,
    DiscoveryStatus,
    EntranceSound,
    EntranceSoundLibrary,
    FavoriteGif,
    FavoriteMeme,
    GiftCode,
    GuildTransferResult,
    MFAState,
    Mention,
    PackDashboard,
    PackSummary,
    RTCRegion,
    ReadState,
    Relationship,
    SavedMessage,
    ScheduledMessage,
    SearchResult,
    SlowmodeState,
    Team,
    Theme,
    UserConnection,
    UserSettings,
    VanityUrl,
    VoiceDebugSession,
    WebAuthnCredential,
)
from fluxer.gateway import GatewayPayload  # noqa: E402
from fluxer.http import HTTPClient, Route  # noqa: E402


class FakeAuthor:
    id = 42
    bot = False
    display_name = "Tester"
    roles = []

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str | None = None, **kwargs):
        self.sent.append(content or "")
        return content


class FakeChannel:
    id = 10
    nsfw = True

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str | None = None, **kwargs):
        self.sent.append(content or "")
        return content

    async def fetch_message(self, message_id: int):
        return message_id


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.author = FakeAuthor()
        self.channel_id = 10
        self.guild_id = None
        self.channel = FakeChannel()
        self.guild = None
        self._http = None
        self.replies: list[str] = []

    async def reply(self, content: str | None = None, **kwargs):
        self.replies.append(content or "")
        return content

    async def send(self, content: str | None = None, **kwargs):
        return await self.reply(content, **kwargs)


async def test_command_conversion() -> None:
    bot = commands.Bot(command_prefix="!")
    seen = []

    @bot.command()
    async def convert(
        ctx: commands.Context, left: int, flag: bool, mode: Literal["fast", "slow"]
    ):
        seen.append((left, flag, mode))

    ctx = await bot.get_context(FakeMessage("!convert 2 yes fast"))
    await bot.invoke(ctx)
    assert seen == [(2, True, "fast")]

    mention_ctx = await bot.get_context(
        FakeMessage("!convert <@1481548097644077825> on slow")
    )
    await bot.invoke(mention_ctx)
    assert seen[-1] == (1481548097644077825, True, "slow")


async def test_command_groups_aliases_and_checks() -> None:
    bot = commands.Bot(command_prefix="!")
    seen = []

    @bot.group(invoke_without_command=True)
    async def root(ctx: commands.Context):
        seen.append("root")

    @root.command(aliases=["plus"])
    @commands.is_nsfw()
    async def add(ctx: commands.Context, left: int, right: int):
        seen.append(left + right)

    ctx = await bot.get_context(FakeMessage("!root plus 3 4"))
    await bot.invoke(ctx)
    assert seen == [7]


async def test_cog_injection() -> None:
    bot = commands.Bot(command_prefix="!")
    seen = []

    class Math(commands.Cog):
        @commands.command()
        async def mul(self, ctx: commands.Context, left: int, right: int):
            seen.append(left * right)

    await bot.add_cog(Math(bot))
    ctx = await bot.get_context(FakeMessage("!mul 3 4"))
    await bot.invoke(ctx)
    assert seen == [12]


async def test_fluxer_help_commands() -> None:
    paginator = commands.Paginator(prefix="[", suffix="]", max_size=12)
    paginator.add_line("abc")
    paginator.add_line("def")
    pages = paginator.pages
    assert pages == ["[\nabc\ndef\n]"]
    assert len(paginator) >= sum(len(page) for page in pages)

    try:
        commands.Paginator(max_size=10).add_line("too long for page")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Paginator should reject oversized lines")

    bot = commands.Bot(command_prefix="!", description="Fluxer helper")

    @bot.command(aliases=["pong"], brief="Reply quickly")
    async def ping(ctx: commands.Context):
        """Reply with latency info."""

    @bot.command(hidden=True)
    async def secret(ctx: commands.Context):
        """Hidden command."""

    @bot.group(invoke_without_command=True, brief="Root tools")
    async def root(ctx: commands.Context):
        """Root command."""

    @root.command(aliases=["kid"], brief="Child command")
    async def child(ctx: commands.Context):
        """Nested command."""

    class Utility(commands.Cog):
        """Utility commands."""

        @commands.command(brief="Cog command")
        async def cogcmd(self, ctx: commands.Context):
            """A command from a cog."""

        @commands.group(invoke_without_command=True, brief="Math tools")
        async def math(self, ctx: commands.Context):
            """Show available math subcommands."""

        @math.command(brief="Add numbers")
        async def add(self, ctx: commands.Context, left: int, right: int):
            """Add two integers and return the result."""

    await bot.add_cog(Utility(bot))

    message = FakeMessage("!help")
    ctx = await bot.get_context(message)
    await bot.invoke(ctx)
    output = "\n".join(message.channel.sent)
    assert "Fluxer helper" in output
    assert "ping" in output
    assert "secret" not in output
    assert "Utility:" in output
    assert "No Category" in output

    command_message = FakeMessage("!help ping")
    command_ctx = await bot.get_context(command_message)
    await bot.invoke(command_ctx)
    command_output = "\n".join(command_message.channel.sent)
    assert "![ping|pong]" in command_output
    assert "Reply with latency info." in command_output

    group_message = FakeMessage("!help root")
    group_ctx = await bot.get_context(group_message)
    await bot.invoke(group_ctx)
    group_output = "\n".join(group_message.channel.sent)
    assert "child" in group_output
    assert "Child command" in group_output

    nested_message = FakeMessage("!help root child")
    nested_ctx = await bot.get_context(nested_message)
    await bot.invoke(nested_ctx)
    nested_output = "\n".join(nested_message.channel.sent)
    assert "!root [child|kid]" in nested_output

    cog_message = FakeMessage("!help Utility")
    cog_ctx = await bot.get_context(cog_message)
    await bot.invoke(cog_ctx)
    cog_output = "\n".join(cog_message.channel.sent)
    assert "Utility commands." in cog_output
    assert "cogcmd" in cog_output

    cog_command_message = FakeMessage("!help cogcmd")
    cog_command_ctx = await bot.get_context(cog_command_message)
    await bot.invoke(cog_command_ctx)
    cog_command_output = "\n".join(cog_command_message.channel.sent)
    assert "!cogcmd" in cog_command_output
    assert "<self>" not in cog_command_output
    assert "<ctx>" not in cog_command_output

    cog_group_message = FakeMessage("!help math")
    cog_group_ctx = await bot.get_context(cog_group_message)
    await bot.invoke(cog_group_ctx)
    cog_group_output = "\n".join(cog_group_message.channel.sent)
    assert "!math" in cog_group_output
    assert "<self>" not in cog_group_output
    assert "<ctx>" not in cog_group_output
    assert "add" in cog_group_output

    cog_subcommand_message = FakeMessage("!help math add")
    cog_subcommand_ctx = await bot.get_context(cog_subcommand_message)
    await bot.invoke(cog_subcommand_ctx)
    cog_subcommand_output = "\n".join(cog_subcommand_message.channel.sent)
    assert "!math add <left> <right>" in cog_subcommand_output
    assert "<self>" not in cog_subcommand_output
    assert "<ctx>" not in cog_subcommand_output

    missing_message = FakeMessage("!help <@123456789012345678>")
    missing_ctx = await bot.get_context(missing_message)
    await bot.invoke(missing_ctx)
    assert "@deleted-user" in "\n".join(missing_message.channel.sent)

    missing_subcommand = FakeMessage("!help ping child")
    missing_subcommand_ctx = await bot.get_context(missing_subcommand)
    await bot.invoke(missing_subcommand_ctx)
    assert "has no subcommands" in "\n".join(missing_subcommand.channel.sent)

    bot.help_command = commands.DefaultHelpCommand(show_hidden=True)
    visible_hidden_message = FakeMessage("!help")
    visible_hidden_ctx = await bot.get_context(visible_hidden_message)
    await bot.invoke(visible_hidden_ctx)
    assert "secret" in "\n".join(visible_hidden_message.channel.sent)

    bot.help_command = None
    assert bot.get_command("help") is None

    minimal_bot = commands.Bot(
        command_prefix="!", help_command=commands.MinimalHelpCommand()
    )

    @minimal_bot.command(aliases=["hi"], brief="Say hello")
    async def hello(ctx: commands.Context):
        """Hello command."""

    minimal_message = FakeMessage("!help hello")
    minimal_ctx = await minimal_bot.get_context(minimal_message)
    await minimal_bot.invoke(minimal_ctx)
    minimal_output = "\n".join(minimal_message.channel.sent)
    assert "**Aliases:** hi" in minimal_output
    assert "!hello" in minimal_output


async def test_fluxer_help_customisation() -> None:
    prepared: list[str | None] = []

    class CustomHelp(commands.HelpCommand):
        async def prepare_help_command(self, ctx, command=None) -> None:
            prepared.append(command)

        def command_not_found(self, string: str) -> str:
            return f"missing:{string}"

        async def send_error_message(self, error: str) -> None:
            await self.context.reply(error)

        async def send_bot_help(self, mapping) -> None:
            await self.context.reply("custom bot help")

    bot = commands.Bot(
        command_prefix="!", help_command=CustomHelp(command_attrs={"name": "assist"})
    )
    assert bot.get_command("assist") is not None
    assert bot.get_command("help") is None

    message = FakeMessage("!assist nope")
    ctx = await bot.get_context(message)
    await bot.invoke(ctx)
    assert prepared == ["nope"]
    assert message.replies == ["missing:nope"]

    class QuietBot(commands.Bot):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.errors: list[Exception] = []

        async def on_command_error(self, context, exception: Exception) -> None:
            self.errors.append(exception)

    blocked_bot = QuietBot(
        command_prefix="!", help_command=commands.DefaultHelpCommand()
    )

    def never(ctx: commands.Context) -> bool:
        return False

    cast(Any, blocked_bot.help_command).add_check(never)
    blocked_message = FakeMessage("!help")
    blocked_ctx = await blocked_bot.get_context(blocked_message)
    await blocked_bot.invoke(blocked_ctx)
    assert blocked_message.channel.sent == []
    assert blocked_bot.errors


def test_gateway_payload() -> None:
    payload = GatewayPayload(
        op=fluxer.GatewayOpcode.DISPATCH, d={"ok": True}, s=1, t="READY"
    )
    assert GatewayPayload.from_json(payload.to_json()).t == "READY"


def test_route_bucket() -> None:
    route = Route(
        "GET",
        "/channels/{channel_id}/messages",
        channel_id=123,
        base_url="https://api.fluxer.app/v1",
    )
    assert route.url.endswith("/channels/123/messages")
    assert route.bucket == "GET /channels/{channel_id}/messages:123"


def test_model_mapping() -> None:
    user = fluxer.User.from_data(
        {
            "id": "1470560041931524138",
            "username": "tester",
            "discriminator": "0001",
            "bot": False,
            "flags": 0,
        }
    )
    assert user.display_name == "tester"


def test_compat_import_surface() -> None:
    assert fluxer.message.Message is fluxer.Message
    assert fluxer.member.Member is fluxer.GuildMember
    assert fluxer.guild.Guild is fluxer.Guild
    assert fluxer.channel.TextChannel is fluxer.Channel
    assert fluxer.permissions.Permissions is fluxer.Permissions
    assert fluxer.flags.Intents is fluxer.Intents
    assert fluxer.role.Role is fluxer.Role
    assert fluxer.user.ClientUser is fluxer.User
    assert issubclass(fluxer.shard.AutoShardedClient, fluxer.Client)
    assert fluxer.account.AuthSession is AuthSession
    assert fluxer.calls.RTCRegion is RTCRegion
    assert fluxer.appinfo.AppInfo is AppInfo
    assert fluxer.appinfo.Team is Team


class FakeHTTP:
    def __init__(self) -> None:
        self.sent_payloads = []
        self.deleted = []
        self.acked = []
        self.acked_pins = []
        self.typing = []
        self.pins_params = []
        self.pinned = []
        self.unpinned = []
        self.guild_list_params = None
        self.created_guilds = []
        self.modified_guilds = []
        self.deleted_guilds = []
        self.left_guilds = []
        self.modified_channels = []
        self.deleted_channels = []
        self.permission_edits = []
        self.permission_deletes = []
        self.channel_positions = None
        self.member_list_params = None
        self.member_searches = []
        self.modified_members = []
        self.modified_current_members = []
        self.added_member_roles = []
        self.removed_member_roles = []
        self.attachment_plans = []
        self.attachment_completions = []
        self.deleted_attachments = []
        self.added_recipients = []
        self.removed_recipients = []

    async def send_message(self, channel_id, **kwargs):
        self.sent_payloads.append((channel_id, kwargs))
        return {
            "id": "100",
            "channel_id": str(channel_id),
            "content": kwargs.get("content", ""),
            "author": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": False,
                "flags": 0,
            },
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    async def get_messages(
        self, channel_id, *, limit=50, before=None, after=None, around=None
    ):
        return [
            {
                "id": str(200 + index),
                "channel_id": str(channel_id),
                "content": f"message {index}",
                "author": {
                    "id": "42",
                    "username": "tester",
                    "discriminator": "0001",
                    "bot": False,
                    "flags": 0,
                },
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
            for index in range(limit)
        ]

    async def delete_messages(self, channel_id, message_ids):
        self.deleted.append((channel_id, list(message_ids)))

    async def modify_channel(self, channel_id, **kwargs):
        self.modified_channels.append((channel_id, kwargs))
        return {
            "id": str(channel_id),
            "guild_id": "20",
            "name": kwargs.get("name", "edited"),
            "type": kwargs.get("type", fluxer.ChannelType.GUILD_TEXT),
            "topic": kwargs.get("topic"),
            "position": kwargs.get("position"),
            "parent_id": kwargs.get("parent_id"),
            "nsfw": kwargs.get("nsfw", False),
            "rate_limit_per_user": kwargs.get("rate_limit_per_user", 0),
            "permission_overwrites": kwargs.get("permission_overwrites", []),
        }

    async def delete_channel(self, channel_id, **kwargs):
        self.deleted_channels.append((channel_id, kwargs))

    async def edit_channel_permissions(self, channel_id, overwrite_id, **kwargs):
        self.permission_edits.append((channel_id, overwrite_id, kwargs))

    async def delete_channel_permissions(self, channel_id, overwrite_id, **kwargs):
        self.permission_deletes.append((channel_id, overwrite_id, kwargs))

    async def acknowledge_message(self, channel_id, message_id):
        self.acked.append((channel_id, message_id))

    async def get_pinned_messages(self, channel_id, *, limit=None, before=None):
        self.pins_params.append((channel_id, limit, before))
        return [
            {
                "message": {
                    "id": "300",
                    "channel_id": str(channel_id),
                    "content": "pinned",
                    "pinned": True,
                    "author": {
                        "id": "42",
                        "username": "tester",
                        "discriminator": "0001",
                        "bot": False,
                        "flags": 0,
                    },
                    "timestamp": "2026-01-01T00:00:00+00:00",
                },
                "pinned_at": "2026-01-01T00:00:00+00:00",
            }
        ]

    async def pin_message(self, channel_id, message_id):
        self.pinned.append((channel_id, message_id))

    async def unpin_message(self, channel_id, message_id):
        self.unpinned.append((channel_id, message_id))

    async def acknowledge_pins(self, channel_id):
        self.acked_pins.append(channel_id)

    async def trigger_typing(self, channel_id):
        self.typing.append(channel_id)

    async def request_message_attachment_uploads(self, channel_id, attachments):
        self.attachment_plans.append((channel_id, attachments))
        return {
            "attachments": [
                {
                    "id": 0,
                    "filename": "hello.txt",
                    "upload_filename": "uploads/hello.txt",
                    "file_size": 5,
                    "content_type": "text/plain",
                    "upload_mode": "singlepart",
                    "upload_url": "https://uploads.invalid/hello",
                }
            ]
        }

    async def complete_multipart_message_attachment_uploads(self, channel_id, uploads):
        self.attachment_completions.append((channel_id, uploads))
        return {"uploads": [{"upload_filename": "uploads/big.bin"}]}

    async def delete_message_attachment(self, channel_id, message_id, attachment_id):
        self.deleted_attachments.append((channel_id, message_id, attachment_id))

    async def get_group_dm_recipient_permissions(self, channel_id, user_id):
        return {
            "channel_id": str(channel_id),
            "user_id": str(user_id),
            "can_manage": True,
        }

    async def add_group_dm_recipient(self, channel_id, user_id):
        self.added_recipients.append((channel_id, user_id))

    async def remove_group_dm_recipient(self, channel_id, user_id, **kwargs):
        self.removed_recipients.append((channel_id, user_id, kwargs))

    async def get_channel_invites(self, channel_id):
        return [{"code": "abc", "channel_id": str(channel_id)}]

    async def create_channel_invite(self, channel_id, **kwargs):
        return {"code": "new", "channel_id": str(channel_id), **kwargs}

    async def get_current_user_guilds(
        self, *, before=None, after=None, limit=None, with_counts=None
    ):
        self.guild_list_params = {
            "before": before,
            "after": after,
            "limit": limit,
            "with_counts": with_counts,
        }
        guilds = [
            {"id": "20", "name": "Guild", "owner_id": "42", "member_count": 5},
            {"id": "21", "name": "Other", "owner_id": "42", "member_count": 2},
        ]
        return guilds[:limit]

    async def get_guild(self, guild_id):
        return {"id": str(guild_id), "name": "Guild", "owner_id": "42"}

    async def get_guild_channels(self, guild_id):
        return [
            {
                "id": "10",
                "guild_id": str(guild_id),
                "name": "general",
                "type": fluxer.ChannelType.GUILD_TEXT,
                "position": 0,
                "nsfw": False,
                "permission_overwrites": [],
            }
        ]

    async def create_guild_channel(self, guild_id, **kwargs):
        return {
            "id": "11",
            "guild_id": str(guild_id),
            "name": kwargs["name"],
            "type": kwargs["type"],
            "topic": kwargs.get("topic"),
            "url": kwargs.get("url"),
            "bitrate": kwargs.get("bitrate"),
            "user_limit": kwargs.get("user_limit"),
            "voice_connection_limit": kwargs.get("voice_connection_limit"),
            "rate_limit_per_user": kwargs.get("rate_limit_per_user"),
            "position": kwargs.get("position"),
            "parent_id": kwargs.get("parent_id"),
            "nsfw": kwargs.get("nsfw", False),
            "permission_overwrites": kwargs.get("permission_overwrites", []),
        }

    async def update_guild_channel_positions(self, guild_id, positions):
        self.channel_positions = (guild_id, positions)

    def _member_data(self, guild_id=20, user_id=42, **kwargs):
        data = {
            "guild_id": str(guild_id),
            "user": {
                "id": str(user_id),
                "username": f"user{user_id}",
                "global_name": "Global",
                "discriminator": "0001",
                "bot": False,
                "flags": 0,
            },
            "nick": kwargs.get("nick", "Nick"),
            "roles": [str(role) for role in kwargs.get("roles", [30])],
            "joined_at": "2026-01-01T00:00:00+00:00",
            "mute": kwargs.get("mute", False),
            "deaf": kwargs.get("deaf", False),
            "communication_disabled_until": kwargs.get("communication_disabled_until"),
        }
        data.update({key: value for key, value in kwargs.items() if value is not None})
        return data

    async def get_guild_member(self, guild_id, user_id):
        return self._member_data(guild_id, user_id)

    async def get_current_guild_member(self, guild_id):
        return self._member_data(guild_id, 42, nick="Current")

    async def get_guild_members(self, guild_id, *, limit=100, after=None):
        self.member_list_params = (guild_id, limit, after)
        return [
            self._member_data(guild_id, 42),
            self._member_data(guild_id, 43, nick="Other", roles=[31]),
        ][:limit]

    async def search_guild_members(self, guild_id, **kwargs):
        self.member_searches.append((guild_id, kwargs))
        return {"members": [self._member_data(guild_id, 43, nick="Search")]}

    async def modify_guild_member(self, guild_id, user_id, **kwargs):
        self.modified_members.append((guild_id, user_id, kwargs))
        return self._member_data(
            guild_id,
            user_id,
            nick=kwargs.get("nick", "Edited"),
            roles=kwargs.get("roles", [30]),
            mute=kwargs.get("mute", False),
            deaf=kwargs.get("deaf", False),
            avatar=kwargs.get("avatar"),
            banner=kwargs.get("banner"),
            accent_color=kwargs.get("accent_color"),
            communication_disabled_until=kwargs.get("communication_disabled_until"),
        )

    async def modify_current_guild_member(self, guild_id, **kwargs):
        self.modified_current_members.append((guild_id, kwargs))
        return self._member_data(guild_id, 42, nick=kwargs.get("nick", "Me"))

    async def add_guild_member_role(self, guild_id, user_id, role_id, **kwargs):
        self.added_member_roles.append((guild_id, user_id, role_id, kwargs))

    async def remove_guild_member_role(self, guild_id, user_id, role_id, **kwargs):
        self.removed_member_roles.append((guild_id, user_id, role_id, kwargs))

    async def get_guild_roles(self, guild_id):
        return [
            {
                "id": "30",
                "name": "Role",
                "color": 0,
                "position": 1,
                "hoist_position": None,
                "permissions": "0",
                "hoist": False,
                "mentionable": False,
            }
        ]

    async def create_guild_role(self, guild_id, **kwargs):
        return {
            "id": "31",
            "name": kwargs.get("name", "new role"),
            "color": kwargs.get("color", 0),
            "position": 2,
            "hoist_position": None,
            "permissions": str(kwargs.get("permissions", 0)),
            "hoist": kwargs.get("hoist", False),
            "mentionable": kwargs.get("mentionable", False),
        }

    async def modify_guild_role(self, guild_id, role_id, **kwargs):
        return {
            "id": str(role_id),
            "name": kwargs.get("name", "edited"),
            "color": kwargs.get("color", 0),
            "position": 2,
            "hoist_position": kwargs.get("hoist_position"),
            "permissions": str(kwargs.get("permissions") or 0),
            "hoist": kwargs.get("hoist", False),
            "mentionable": kwargs.get("mentionable", False),
        }

    async def delete_guild_role(self, guild_id, role_id):
        self.deleted_role = (guild_id, role_id)

    async def update_guild_role_positions(self, guild_id, positions):
        self.role_positions = (guild_id, positions)
        return [
            {
                "id": item["id"],
                "name": "Role",
                "color": 0,
                "position": item["position"],
                "permissions": "0",
                "hoist": False,
                "mentionable": False,
            }
            for item in positions
        ]

    async def update_role_hoist_positions(self, guild_id, positions):
        self.role_hoist_positions = (guild_id, positions)

    async def reset_role_hoist_positions(self, guild_id):
        self.reset_hoist_positions = guild_id

    async def get_guild_bans(self, guild_id):
        return [
            {
                "user": {
                    "id": "42",
                    "username": "banned",
                    "discriminator": "0001",
                    "bot": False,
                    "flags": 0,
                },
                "reason": "because",
                "moderator_id": "99",
                "banned_at": "2026-01-01T00:00:00+00:00",
                "expires_at": None,
            }
        ]

    async def get_oauth_applications_me(self):
        return {
            "id": "99",
            "name": "Bot App",
            "redirect_uris": ["https://example.invalid/callback"],
            "bot_public": True,
            "bot_require_code_grant": False,
            "bot": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": True,
                "flags": 0,
            },
        }

    async def get_user_applications(self):
        return [
            {
                "id": "99",
                "name": "Bot App",
                "redirect_uris": [],
                "bot_public": True,
                "bot_require_code_grant": False,
            }
        ]

    async def get_oauth_application(self, application_id):
        return {
            "id": str(application_id),
            "name": "Fetched App",
            "redirect_uris": [],
            "bot_public": False,
            "bot_require_code_grant": True,
        }

    async def get_gift_code(self, code):
        return {
            "code": code,
            "duration_type": "months",
            "duration_quantity": 1,
            "redeemed": False,
            "created_by": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": False,
                "flags": 0,
            },
        }

    async def redeem_gift_code(self, code):
        self.redeemed_gift = code

    async def get_user_gifts(self):
        return [
            {
                "code": "gift",
                "duration_type": "months",
                "duration_quantity": 1,
                "created_at": "2026-01-01T00:00:00+00:00",
                "created_by": {
                    "id": "42",
                    "username": "tester",
                    "discriminator": "0001",
                    "bot": False,
                    "flags": 0,
                },
                "redeemed_at": None,
                "redeemed_by": None,
            }
        ]

    async def list_user_packs(self):
        return {
            "emoji": {
                "installed_limit": 50,
                "created_limit": 10,
                "installed": [
                    {
                        "id": "600",
                        "name": "Faces",
                        "description": "emoji pack",
                        "type": "emoji",
                        "creator_id": "42",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
                "created": [],
            },
            "sticker": {
                "installed_limit": 50,
                "created_limit": 10,
                "installed": [],
                "created": [],
            },
        }

    async def create_pack(self, pack_type, *, name, description=None):
        return {
            "id": "601",
            "name": name,
            "description": description,
            "type": pack_type,
            "creator_id": "42",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    async def update_pack(self, pack_id, **payload):
        return {
            "id": str(pack_id),
            "name": payload.get("name", "Updated"),
            "description": payload.get("description"),
            "type": "emoji",
            "creator_id": "42",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
        }

    async def delete_pack(self, pack_id):
        self.deleted_pack = pack_id

    async def install_pack(self, pack_id):
        self.installed_pack = pack_id

    async def uninstall_pack(self, pack_id):
        self.uninstalled_pack = pack_id

    async def list_pack_invites(self, pack_id):
        return [{"code": "pack", "pack_id": str(pack_id)}]

    async def create_pack_invite(self, pack_id, **payload):
        return {"code": "newpack", "pack_id": str(pack_id), **payload}

    async def list_pack_emojis(self, pack_id):
        return [{"id": "700", "name": "wave"}]

    async def create_pack_emoji(self, pack_id, **payload):
        return {"id": "701", "name": payload.get("name", "wave")}

    async def bulk_create_pack_emojis(self, pack_id, emojis):
        return {"created": [{"id": "702", "name": emojis[0]["name"]}]}

    async def update_pack_emoji(self, pack_id, emoji_id, **payload):
        return {"id": str(emoji_id), "name": payload.get("name", "updated")}

    async def delete_pack_emoji(self, pack_id, emoji_id, *, purge=None):
        self.deleted_pack_emoji = (pack_id, emoji_id, purge)

    async def list_pack_stickers(self, pack_id):
        return [{"id": "800", "name": "sticker", "description": "hi"}]

    async def create_pack_sticker(self, pack_id, **payload):
        return {
            "id": "801",
            "name": payload.get("name", "sticker"),
            "description": payload.get("description"),
        }

    async def bulk_create_pack_stickers(self, pack_id, stickers):
        return {"created": [{"id": "802", "name": stickers[0]["name"]}]}

    async def update_pack_sticker(self, pack_id, sticker_id, **payload):
        return {
            "id": str(sticker_id),
            "name": payload.get("name", "updated"),
            "description": payload.get("description"),
        }

    async def delete_pack_sticker(self, pack_id, sticker_id, *, purge=None):
        self.deleted_pack_sticker = (pack_id, sticker_id, purge)

    async def get_entrance_sound_library(self):
        return {
            "sounds": [
                {
                    "id": "900",
                    "name": "Hello",
                    "hash": "abc",
                    "extension": "mp3",
                    "content_type": "audio/mpeg",
                    "duration_ms": 1000,
                    "size_bytes": 1234,
                    "url": "https://cdn.invalid/sound.mp3",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "selections": [{"scope_id": "global", "sound_id": "900"}],
        }

    async def upload_entrance_sound(self, *, name, audio):
        return {
            "id": "901",
            "name": name,
            "hash": "def",
            "extension": "mp3",
            "content_type": "audio/mpeg",
            "duration_ms": 1000,
            "size_bytes": 1234,
            "url": "https://cdn.invalid/upload.mp3",
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    async def rename_entrance_sound(self, sound_id, *, name):
        return {
            "id": str(sound_id),
            "name": name,
            "hash": "abc",
            "extension": "mp3",
            "content_type": "audio/mpeg",
            "duration_ms": 1000,
            "size_bytes": 1234,
            "url": "https://cdn.invalid/sound.mp3",
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    async def delete_entrance_sound(self, sound_id):
        self.deleted_entrance_sound = sound_id

    async def set_entrance_sound_selection(self, scope_id, sound_id):
        self.entrance_sound_selection = (scope_id, sound_id)

    async def play_entrance_sound(self, channel_id, sound_id):
        self.played_entrance_sound = (channel_id, sound_id)

    async def create_theme(self, css):
        return {"id": "abcdef1234567890"}

    async def create_guild(self, *, name, icon=None, **kwargs):
        self.created_guilds.append((name, icon, kwargs))
        return {"id": "30", "name": name, "owner_id": "42", **kwargs}

    async def modify_guild(self, guild_id, **kwargs):
        self.modified_guilds.append((guild_id, kwargs))
        return {
            "id": str(guild_id),
            "name": kwargs.get("name", "Guild"),
            "owner_id": "42",
        }

    async def delete_guild(self, guild_id):
        self.deleted_guilds.append(guild_id)

    async def leave_guild(self, guild_id):
        self.left_guilds.append(guild_id)

    async def get_guild_invites(self, guild_id):
        return [{"code": "guild", "guild_id": str(guild_id)}]

    async def get_guild_audit_logs(self, guild_id, **kwargs):
        return {"audit_log_entries": [{"id": "1", "action_type": "test"}], "users": []}

    async def get_guild_stickers(self, guild_id):
        return [{"id": "55", "name": "wave", "guild_id": str(guild_id)}]

    async def get_guild_discovery_status(self, guild_id):
        return {"guild_id": str(guild_id), "status": "eligible", "eligible": True}

    async def apply_for_discovery(self, guild_id, **payload):
        return {"guild_id": str(guild_id), "status": "pending", **payload}

    async def edit_discovery_application(self, guild_id, **payload):
        return {"guild_id": str(guild_id), "status": "pending", **payload}

    async def withdraw_discovery_application(self, guild_id):
        self.withdrawn_discovery = guild_id

    async def join_discovery_guild(self, guild_id):
        self.joined_discovery = guild_id

    async def get_guild_vanity_url(self, guild_id):
        return {"code": "cool", "uses": 3}

    async def update_guild_vanity_url(self, guild_id, code):
        return {"code": code, "uses": 3}

    async def transfer_guild_ownership(self, guild_id, new_owner_id, **payload):
        return {"id": str(guild_id), "owner_id": str(new_owner_id), **payload}

    async def bulk_create_guild_emojis(self, guild_id, emojis):
        return {"created": emojis}

    async def bulk_create_guild_stickers(self, guild_id, stickers):
        return {"created": stickers}

    async def clone_guild_emoji(self, guild_id, **payload):
        return {
            "id": "77",
            "name": payload.get("name", "wave"),
            "guild_id": str(guild_id),
        }

    async def clone_guild_sticker(self, guild_id, **payload):
        return {
            "id": "88",
            "name": payload.get("name", "wave"),
            "guild_id": str(guild_id),
        }

    async def save_message(self, message_id, *, channel_id=None):
        self.saved = (message_id, channel_id)

    async def unsave_message(self, message_id):
        self.unsaved = message_id

    async def execute_webhook(self, webhook_id, token, **kwargs):
        self.webhook_execute = (webhook_id, token, kwargs)
        return {
            "id": "700",
            "channel_id": "10",
            "content": kwargs.get("content", ""),
            "author": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": True,
                "flags": 0,
            },
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    async def edit_webhook_message(self, webhook_id, token, message_id, **kwargs):
        self.webhook_edit = (webhook_id, token, message_id, kwargs)
        return {
            "id": str(message_id),
            "channel_id": "10",
            "content": kwargs.get("content", ""),
            "author": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": True,
                "flags": 0,
            },
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    async def delete_webhook_message(self, webhook_id, token, message_id):
        self.webhook_delete = (webhook_id, token, message_id)

    async def execute_github_webhook(self, webhook_id, token, payload):
        self.webhook_github = (webhook_id, token, payload)

    async def execute_instatus_webhook(self, webhook_id, token, payload):
        self.webhook_instatus = (webhook_id, token, payload)

    async def execute_slack_webhook(self, webhook_id, token, payload):
        self.webhook_slack = (webhook_id, token, payload)
        return "ok"


async def test_message_channel_parity() -> None:
    http: Any = FakeHTTP()
    channel: Any = fluxer.Channel(id=10, type=fluxer.ChannelType.GUILD_TEXT, _http=http)
    allowed_mentions = fluxer.AllowedMentions.none()
    sent = await channel.send("hello", allowed_mentions=allowed_mentions)
    assert http.sent_payloads[0][1]["allowed_mentions"].to_dict()["parse"] == []
    assert sent.jump_url.endswith("/@me/10/100")

    history = []
    async for message in channel.history(limit=2):
        history.append(message)
    assert [message.content for message in history] == ["message 0", "message 1"]

    deleted = await channel.purge(limit=2, check=lambda message: message.id == 200)
    assert [message.id for message in deleted] == [200]
    assert http.deleted[-1] == (10, [200])

    partial = channel.get_partial_message(999)
    assert partial.jump_url.endswith("/@me/10/999")
    await partial.ack()
    assert http.acked == [(10, 999)]

    pins = await channel.fetch_pinned_messages(
        limit=1, before="2026-01-02T00:00:00+00:00"
    )
    assert pins[0].content == "pinned"
    assert pins[0].pinned is True
    assert http.pins_params == [(10, 1, "2026-01-02T00:00:00+00:00")]
    await pins[0].unpin()
    assert pins[0].pinned is False
    await pins[0].pin()
    assert pins[0].pinned is True
    await channel.ack_pins()
    assert http.unpinned == [(10, 300)]
    assert http.pinned == [(10, 300)]
    assert http.acked_pins == [10]

    await channel.typing()
    async with channel.typing():
        pass
    assert http.typing == [10, 10]


async def test_invites_audit_stickers() -> None:
    http: Any = FakeHTTP()
    channel: Any = fluxer.Channel(id=10, type=fluxer.ChannelType.GUILD_TEXT, _http=http)
    guild: Any = fluxer.Guild(id=20, name="Guild", _http=http)

    assert (await channel.invites())[0].code == "abc"
    assert (await channel.create_invite()).code == "new"
    assert (await guild.invites())[0].code == "guild"
    assert (await guild.audit_logs()).entries[0].action_type == "test"
    assert (await guild.fetch_stickers())[0].name == "wave"
    assert (await guild.discovery_status()).eligible is True
    assert (await guild.apply_for_discovery(description="hi")).status == "pending"
    assert (
        await guild.edit_discovery_application(description="new")
    ).description == "new"
    await guild.withdraw_discovery_application()
    await guild.join_discovery()
    assert http.withdrawn_discovery == 20
    assert http.joined_discovery == 20
    assert (await guild.get_vanity_url()).code == "cool"
    assert (await guild.update_vanity_url("new")).code == "new"
    assert (await guild.transfer_ownership(42)).owner_id == 42
    assert (await guild.bulk_create_emojis([{"id": "1"}])).items == [{"id": "1"}]
    assert (await guild.bulk_create_stickers([{"id": "2"}])).items == [{"id": "2"}]
    assert (await guild.clone_emoji(name="party")).name == "party"
    assert (await guild.clone_sticker(name="party")).name == "party"
    assert str(fluxer.Colour.from_str("rgb(1, 2, 3)")) == "#010203"


async def test_guild_lifecycle_helpers() -> None:
    http: Any = FakeHTTP()
    client: Any = fluxer.Client()
    client._http = http

    guilds = await client.fetch_guilds(limit=2, with_counts=True).flatten()
    assert [guild.name for guild in guilds] == ["Guild", "Other"]
    assert http.guild_list_params == {
        "before": None,
        "after": None,
        "limit": 2,
        "with_counts": True,
    }
    assert client.get_guild(20) is guilds[0]

    fetched = await client.fetch_guild("20")
    assert fetched.id == 20

    created = await client.create_guild("New Guild", preferred_locale="en-US")
    assert created.name == "New Guild"
    assert http.created_guilds == [("New Guild", None, {"preferred_locale": "en-US"})]
    assert client.get_guild(30) is created

    edited = await guilds[0].edit(name="Renamed")
    assert edited.name == "Renamed"
    assert guilds[0].name == "Renamed"
    await guilds[0].leave()
    await guilds[0].delete()
    assert http.modified_guilds == [(20, {"name": "Renamed", "icon": None})]
    assert http.left_guilds == [20]
    assert http.deleted_guilds == [20]


async def test_channel_management_helpers() -> None:
    http: Any = FakeHTTP()
    guild: Any = fluxer.Guild(id=20, name="Guild", _http=http)

    channels = await guild.fetch_channels()
    assert channels[0].name == "general"
    assert channels[0].guild is guild

    text = await guild.create_text_channel("chat", topic="hello", rate_limit_per_user=5)
    assert text.type == fluxer.ChannelType.GUILD_TEXT
    assert text.topic == "hello"
    assert text.guild is guild

    voice = await guild.create_voice_channel("voice", bitrate=64000, user_limit=5)
    assert voice.type == fluxer.ChannelType.GUILD_VOICE
    assert voice.bitrate == 64000
    assert voice.user_limit == 5

    category = await guild.create_category("category", position=2)
    assert category.type == fluxer.ChannelType.GUILD_CATEGORY
    assert category.position == 2

    link = await guild.create_link_channel("docs", url="https://example.invalid")
    assert link.type == cast(Any, fluxer.ChannelType).GUILD_LINK
    assert link.url == "https://example.invalid"

    await guild.edit_channel_positions({channels[0]: 3})
    assert http.channel_positions == (20, [{"id": "10", "position": 3}])

    edited = await channels[0].edit(name="renamed", rate_limit_per_user=10)
    assert edited.name == "renamed"
    assert edited.rate_limit_per_user == 10
    assert http.modified_channels[-1][1]["name"] == "renamed"

    await channels[0].set_permissions(
        30, send_messages=True, read_message_history=False
    )
    overwrite_payload = http.permission_edits[-1][2]
    assert overwrite_payload["allow"] == int(fluxer.Permissions.SEND_MESSAGES)
    assert overwrite_payload["deny"] == int(fluxer.Permissions.READ_MESSAGE_HISTORY)

    await channels[0].set_permissions(30)
    assert http.permission_deletes[-1] == (10, 30, {"reason": None})

    await channels[0].delete(silent=True, delete_messages=False)
    assert http.deleted_channels[-1] == (
        10,
        {
            "silent": True,
            "delete_messages": False,
            "password": None,
            "mfa_method": None,
            "mfa_code": None,
            "webauthn_response": None,
            "webauthn_challenge": None,
        },
    )


async def test_guild_roles_and_bans() -> None:
    http: Any = FakeHTTP()
    guild: Any = fluxer.Guild(id=20, name="Guild", _http=http)

    role = (await guild.fetch_roles())[0]
    assert role.name == "Role"
    assert role.hoist_position is None

    created = await guild.create_role(name="Staff", permissions=8, hoist=True)
    assert created.name == "Staff"
    assert created.permissions == 8
    edited = await created.edit(name="Admin", hoist_position=1)
    assert edited.name == "Admin"
    assert edited.hoist_position == 1
    await edited.delete()
    assert http.deleted_role == (20, 31)

    moved = await guild.edit_role_positions({role: 3})
    assert moved[0].position == 3
    assert http.role_positions == (20, [{"id": "30", "position": 3}])
    await guild.update_role_hoist_positions({role: 2})
    assert http.role_hoist_positions == (20, [{"id": "30", "hoist_position": 2}])
    await guild.reset_role_hoist_positions()
    assert http.reset_hoist_positions == 20

    ban = BanEntry.from_data((await http.get_guild_bans(20))[0])
    assert ban.user.username == "banned"
    assert ban.moderator_id == 99
    assert (await guild.bans())[0].reason == "because"
    assert (await guild.fetch_ban(42)).user.id == 42


async def test_guild_member_helpers() -> None:
    http: Any = FakeHTTP()
    guild: Any = fluxer.Guild(id=20, name="Guild", _http=http)
    client: Any = fluxer.Client()
    client._http = http

    member = await guild.fetch_member(42)
    assert member.display_name == "Nick"
    assert member.has_role(30)

    current = await guild.me()
    assert current.nick == "Current"

    members = await guild.fetch_members(limit=2, after=41)
    assert [member.user.id for member in members] == [42, 43]
    assert http.member_list_params == (20, 2, 41)

    found = await guild.search_members(query="Search", role_ids=[31], limit=1)
    assert found[0].nick == "Search"
    assert http.member_searches[-1][1]["role_ids"] == [31]

    fetched = await client.fetch_member(20, 42)
    assert client.get_member(20, 42) is fetched
    assert (await client.fetch_current_member(20)).nick == "Current"
    assert (await client.search_members(20, query="Other"))[0].user.id == 43

    role = fluxer.Role(id=31, name="Role", guild_id=20, _http=http)
    await member.add_roles(role, 32, reason="grant")
    assert 31 in member.roles and 32 in member.roles
    assert http.added_member_roles[-2:] == [
        (20, 42, 31, {"reason": "grant"}),
        (20, 42, 32, {"reason": "grant"}),
    ]

    await member.remove_roles(role, 32, reason="revoke")
    assert 31 not in member.roles and 32 not in member.roles
    assert http.removed_member_roles[-2:] == [
        (20, 42, 31, {"reason": "revoke"}),
        (20, 42, 32, {"reason": "revoke"}),
    ]

    edited = await member.edit(
        nick="Edited",
        roles=[30, 31],
        mute=True,
        avatar="data:image/png;base64,abc",
        banner="data:image/png;base64,def",
        accent_color=0x336699,
        bio="bio",
        pronouns="they/them",
        timeout_reason="test",
    )
    assert edited.nick == "Edited"
    assert edited.roles == [30, 31]
    assert edited.mute is True
    assert edited.avatar_hash == "data:image/png;base64,abc"
    assert edited.banner == "data:image/png;base64,def"
    assert edited.accent_color == 0x336699
    assert http.modified_members[-1][2]["bio"] == "bio"
    assert http.modified_members[-1][2]["timeout_reason"] == "test"


async def test_attachment_upload_lifecycle() -> None:
    http: Any = FakeHTTP()
    client: Any = fluxer.Client()
    client._http = http
    channel: Any = fluxer.Channel(id=10, type=fluxer.ChannelType.GUILD_TEXT, _http=http)

    file: Any = fluxer.File(b"hello", filename="hello.txt")
    spec = AttachmentUploadSpec.from_data(file.to_upload_spec(0))
    assert spec.content_type == "text/plain"

    client_plan = await client.request_attachment_uploads(10, [spec])
    assert isinstance(client_plan, AttachmentUploadPlan)
    assert client_plan.attachments[0].upload_url == "https://uploads.invalid/hello"
    assert client_plan.attachments[0].to_attachment_payload() == {
        "id": 0,
        "filename": "hello.txt",
        "uploaded_filename": "uploads/hello.txt",
    }

    channel_plan = await channel.request_attachment_uploads([spec.to_dict()])
    assert channel_plan.attachments[0].filename == "hello.txt"

    completed = await channel.complete_attachment_uploads(
        [{"upload_filename": "uploads/big.bin", "upload_id": "multi"}]
    )
    assert isinstance(completed, CompletedAttachmentUploadList)
    assert completed.uploads[0].upload_filename == "uploads/big.bin"

    upload = AttachmentUpload.from_data(
        {
            "id": 1,
            "filename": "big.bin",
            "upload_filename": "uploads/big.bin",
            "file_size": 11_000_000,
            "content_type": "application/octet-stream",
            "upload_mode": "multipart",
            "upload_id": "multi",
            "part_size": 5_500_000,
            "parts": [{"part_number": 1, "upload_url": "https://uploads.invalid/part"}],
        }
    )
    assert upload.is_multipart is True
    assert upload.parts[0].part_number == 1

    message: Any = fluxer.Message.from_data(
        {
            "id": "500",
            "channel_id": "10",
            "content": "with attachment",
            "author": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": False,
                "flags": 0,
            },
            "timestamp": "2026-01-01T00:00:00+00:00",
            "attachments": [
                {
                    "id": "900",
                    "filename": "hello.txt",
                    "size": 5,
                    "url": "https://cdn.invalid/hello.txt",
                    "content_type": "text/plain",
                }
            ],
        },
        http,
    )
    await message.attachments[0].delete()
    await message.delete_attachment(900)
    assert http.deleted_attachments == [(10, 500, 900), (10, 500, 900)]


async def test_group_dm_recipient_helpers() -> None:
    http: Any = FakeHTTP()
    client: Any = fluxer.Client()
    client._http = http
    channel: Any = fluxer.Channel(id=10, type=fluxer.ChannelType.GROUP_DM, _http=http)

    permissions = await client.fetch_group_dm_recipient_permissions(10, 42)
    assert permissions["can_manage"] is True

    await client.add_group_dm_recipient(10, 42)
    await client.remove_group_dm_recipient(
        10,
        42,
        silent=True,
        delete_messages=True,
        password="pw",
    )
    await channel.add_recipient(43)
    await channel.remove_recipient(43, silent=False)

    assert http.added_recipients == [(10, 42), (10, 43)]
    assert http.removed_recipients == [
        (
            10,
            42,
            {
                "silent": True,
                "delete_messages": True,
                "password": "pw",
                "mfa_method": None,
                "mfa_code": None,
                "webauthn_response": None,
                "webauthn_challenge": None,
            },
        ),
        (
            10,
            43,
            {
                "silent": False,
                "delete_messages": None,
                "password": None,
                "mfa_method": None,
                "mfa_code": None,
                "webauthn_response": None,
                "webauthn_challenge": None,
            },
        ),
    ]


async def test_client_cache_dispatch() -> None:
    client = fluxer.Client(max_messages=5)
    client._http = cast(Any, FakeHTTP())
    seen = []
    wait_ready = asyncio.create_task(client.wait_until_ready())
    wait_message = client.wait_for(
        "message", check=lambda message: message.content == "old"
    )

    @client.event
    async def on_message(message):
        seen.append(("message", message.id))

    @client.event
    async def on_message_edit(before, after=None):
        seen.append(("edit", before.content, getattr(after, "content", None)))

    @client.event
    async def on_raw_message_delete(raw):
        seen.append(("raw_delete", raw.message_id))

    @client.event
    async def on_message_delete(message):
        seen.append(
            ("delete", message.id if hasattr(message, "id") else message.message_id)
        )

    @client.event
    async def on_raw_reaction_add(raw):
        seen.append(("raw_reaction", raw.message_id))

    @client.event
    async def on_reaction_add(reaction, user):
        seen.append(("reaction", reaction.count, user))

    @client.event
    async def on_fluxer_event(raw):
        seen.append(("fluxer", raw.name))

    message_data = {
        "id": "500",
        "channel_id": "10",
        "content": "old",
        "author": {
            "id": "42",
            "username": "tester",
            "discriminator": "0001",
            "bot": False,
            "flags": 0,
        },
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    assert not client.is_ready()
    await client._dispatch(
        "READY",
        {
            "user": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": True,
                "flags": 0,
            },
            "guilds": [
                {
                    "id": "20",
                    "name": "Guild",
                    "channels": [
                        {
                            "id": "10",
                            "type": int(fluxer.ChannelType.GUILD_TEXT),
                            "name": "general",
                            "guild_id": "20",
                        }
                    ],
                    "members": [
                        {
                            "user": {
                                "id": "42",
                                "username": "tester",
                                "discriminator": "0001",
                                "bot": False,
                                "flags": 0,
                            },
                            "roles": [],
                            "guild_id": "20",
                        }
                    ],
                }
            ],
        },
    )
    await asyncio.wait_for(wait_ready, timeout=1)
    assert client.is_ready()
    assert client.get_channel(10) is not None

    await client._dispatch("MESSAGE_CREATE", message_data)
    cached_message = client.get_message(500)
    assert cached_message is not None
    assert cached_message.channel is client.get_channel(10)
    cached_channel = cached_message.channel
    assert cached_channel is not None
    assert cached_channel.name == "general"
    assert cached_message.guild is client.get_guild(20)
    assert await asyncio.wait_for(wait_message, timeout=1) == client.get_message(500)
    await client._dispatch("MESSAGE_UPDATE", {**message_data, "content": "new"})
    await client._dispatch(
        "MESSAGE_REACTION_ADD",
        {
            "message_id": "500",
            "channel_id": "10",
            "user_id": "42",
            "emoji": {"name": "👍"},
        },
    )
    await client._dispatch("SAVED_MESSAGE_CREATE", {"id": "1"})
    await client._dispatch("MESSAGE_DELETE", {"id": "500", "channel_id": "10"})

    assert ("message", 500) in seen
    assert ("edit", "old", "new") in seen
    assert ("raw_reaction", 500) in seen
    assert ("reaction", 1, 42) in seen
    assert ("fluxer", "SAVED_MESSAGE_CREATE") in seen
    assert ("raw_delete", 500) in seen
    assert ("delete", 500) in seen


async def test_fluxer_models_and_client_helpers() -> None:
    http: Any = FakeHTTP()
    message: Any = fluxer.Message.from_data(
        {
            "id": "500",
            "channel_id": "10",
            "content": "save me",
            "author": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": False,
                "flags": 0,
            },
            "timestamp": "2026-01-01T00:00:00+00:00",
        },
        http,
    )
    await message.save()
    await message.unsave()
    assert http.saved == (500, 10)
    assert http.unsaved == 500

    assert (
        SavedMessage.from_data({"message_id": "500", "channel_id": "10"}).message_id
        == 500
    )
    assert (
        ScheduledMessage.from_data({"id": "abc", "status": "pending"}).status
        == "pending"
    )
    assert Mention.from_data({"message_id": "500"}).message_id == 500
    assert Relationship.from_data({"user_id": "42", "type": "friend"}).user_id == 42
    assert FavoriteMeme.from_data({"id": "m1", "tags": ["fun"]}).tags == ["fun"]
    assert SearchResult.from_data({"messages": []}).messages == []
    assert ReadState.from_data({"id": "10", "mention_count": 2}).mention_count == 2
    assert (
        FavoriteGif.from_data(
            {"url": "https://example.invalid/a.gif", "proxy_url": "cdn"}
        ).proxy_url
        == "cdn"
    )
    assert DiscoveryGuild.from_data({"id": "20", "name": "Guild"}).name == "Guild"
    assert VanityUrl.from_data({"code": "cool", "uses": 3}).uses == 3
    assert BulkOperationResult.from_data({"created": [{"id": "1"}]}).items == [
        {"id": "1"}
    ]
    assert (
        DiscoveryApplication.from_data({"guild_id": "20", "status": "pending"}).status
        == "pending"
    )
    assert (
        DiscoveryStatus.from_data({"guild_id": "20", "eligible": True}).eligible is True
    )
    assert GuildTransferResult.from_data({"id": "20", "owner_id": "42"}).owner_id == 42
    assert BulkEmojiResult.from_data({"created": [{"id": "1"}]}).items == [{"id": "1"}]
    assert BulkStickerResult.from_data({"created": [{"id": "2"}]}).items == [
        {"id": "2"}
    ]
    assert AuthSession.from_data({"id": "s1", "current": True}).current is True
    assert (
        MFAState.from_data({"totp": True, "webauthn": False, "has_mfa": True}).has_mfa
        is True
    )
    assert WebAuthnCredential.from_data({"id": "cred", "name": "key"}).name == "key"
    assert UserSettings.from_data({"theme": "dark", "status": "online"}).theme == "dark"
    assert UserConnection.from_data({"id": "c1", "type": "github"}).type == "github"
    assert AuthorizedIP.from_data({"ip": "127.0.0.1"}).ip == "127.0.0.1"
    assert DataHarvest.from_data({"id": "h1", "status": "pending"}).status == "pending"
    gift = GiftCode.from_data(
        {
            "code": "gift",
            "duration_type": "months",
            "duration_quantity": 1,
            "redeemed": False,
            "created_by": {
                "id": "42",
                "username": "tester",
                "discriminator": "0001",
                "bot": False,
                "flags": 0,
            },
        }
    )
    assert gift.code == "gift"
    assert gift.created_by and gift.created_by.username == "tester"
    pack = PackSummary.from_data(
        {
            "id": "600",
            "name": "Faces",
            "description": "emoji pack",
            "type": "emoji",
            "creator_id": "42",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    )
    assert pack.id == 600
    dashboard = PackDashboard.from_data(
        {
            "emoji": {
                "installed_limit": 50,
                "created_limit": 10,
                "installed": [pack.raw_data],
                "created": [],
            },
            "sticker": {
                "installed_limit": 50,
                "created_limit": 10,
                "installed": [],
                "created": [],
            },
        }
    )
    assert dashboard.emoji.installed[0].name == "Faces"
    sound_library = EntranceSoundLibrary.from_data(
        {
            "sounds": [
                {
                    "id": "900",
                    "name": "Hello",
                    "hash": "abc",
                    "extension": "mp3",
                    "content_type": "audio/mpeg",
                    "duration_ms": 1000,
                    "size_bytes": 1234,
                    "url": "https://cdn.invalid/sound.mp3",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "selections": [{"scope_id": "global", "sound_id": "900"}],
        }
    )
    assert sound_library.sounds[0].duration_ms == 1000
    assert sound_library.selections[0].sound_id == 900
    assert EntranceSound.from_data(sound_library.sounds[0].raw_data).name == "Hello"
    assert Theme.from_data({"id": "abcdef1234567890"}).id == "abcdef1234567890"
    assert (
        CallEligibility.from_data({"channel_id": "10", "ringable": True}).ringable
        is True
    )
    assert RTCRegion.from_data({"id": "us", "name": "US"}).name == "US"
    assert CallState.from_data({"channel_id": "10", "region": "us"}).region == "us"
    assert (
        VoiceDebugSession.from_data({"enabled": True, "session_id": "v"}).enabled
        is True
    )
    assert SlowmodeState.from_data({"channel_id": "10", "interval": 5}).interval == 5
    assert Team.from_data({"id": "5", "name": "Team"}).name == "Team"
    app = AppInfo.from_data(
        {
            "id": "99",
            "name": "Bot App",
            "redirect_uris": ["https://example.invalid/callback"],
            "bot_public": True,
            "bot_require_code_grant": False,
            "team": {"id": "5", "name": "Team"},
        }
    )
    assert app.name == "Bot App"
    assert app.team and app.team.id == 5

    client: Any = fluxer.Client()
    client._http = http
    assert (await client.application_info()).bot.username == "tester"
    assert (await client.fetch_applications())[0].id == 99
    assert (await client.fetch_application(100)).bot_require_code_grant is True
    assert (await client.fetch_gift_code("gift")).duration_quantity == 1
    await client.redeem_gift_code("gift")
    assert http.redeemed_gift == "gift"
    assert (await client.fetch_gifts())[0].code == "gift"
    assert (await client.fetch_packs()).emoji.installed[0].id == 600
    assert (await client.create_pack("emoji", name="Faces")).id == 601
    assert (await client.update_pack(601, name="Better")).name == "Better"
    await client.delete_pack(601)
    assert http.deleted_pack == 601
    await client.install_pack(600)
    await client.uninstall_pack(600)
    assert http.installed_pack == 600
    assert http.uninstalled_pack == 600
    assert (await client.fetch_pack_invites(600))[0].code == "pack"
    assert (await client.create_pack_invite(600, max_uses=1)).code == "newpack"
    assert (await client.fetch_pack_emojis(600))[0].name == "wave"
    assert (await client.create_pack_emoji(600, name="wave")).id == 701
    assert (await client.bulk_create_pack_emojis(600, [{"name": "wave"}])).items[0][
        "id"
    ] == "702"
    assert (await client.update_pack_emoji(600, 700, name="new")).name == "new"
    await client.delete_pack_emoji(600, 700, purge=True)
    assert http.deleted_pack_emoji == (600, 700, True)
    assert (await client.fetch_pack_stickers(600))[0].name == "sticker"
    assert (await client.create_pack_sticker(600, name="sticker")).id == 801
    assert (await client.bulk_create_pack_stickers(600, [{"name": "sticker"}])).items[
        0
    ]["id"] == "802"
    assert (await client.update_pack_sticker(600, 800, name="new")).name == "new"
    await client.delete_pack_sticker(600, 800, purge=False)
    assert http.deleted_pack_sticker == (600, 800, False)
    assert (await client.fetch_entrance_sound_library()).sounds[0].id == 900
    assert (await client.upload_entrance_sound(name="Hi", audio="data")).name == "Hi"
    assert (await client.rename_entrance_sound(900, name="Bye")).name == "Bye"
    await client.delete_entrance_sound(900)
    assert http.deleted_entrance_sound == 900
    await client.set_entrance_sound_selection("global", 900)
    assert http.entrance_sound_selection == ("global", 900)
    await client.play_entrance_sound(10, 900)
    assert http.played_entrance_sound == (10, 900)
    assert (await client.create_theme("body{}")).id == "abcdef1234567890"


async def test_webhook_parity() -> None:
    http: Any = FakeHTTP()
    webhook = fluxer.Webhook.from_url(
        "https://api.fluxer.app/v1/webhooks/123/token-value", http=http
    )
    assert webhook.id == 123
    assert webhook.token == "token-value"

    message = await webhook.send(
        "hello", wait=True, allowed_mentions=fluxer.AllowedMentions.none()
    )
    assert isinstance(message, fluxer.WebhookMessage)
    assert message.id == 700
    assert http.webhook_execute[2]["allowed_mentions"].to_dict()["parse"] == []

    edited = await webhook.edit_message(700, content="edited")
    assert edited.content == "edited"
    await edited.delete()
    assert http.webhook_delete == (123, "token-value", 700)

    await webhook.execute_github({"action": "opened"})
    await webhook.execute_instatus({"trigger": "incident.updated"})
    assert await webhook.execute_slack({"text": "deploy complete"}) == "ok"
    assert http.webhook_github == (123, "token-value", {"action": "opened"})
    assert http.webhook_instatus == (
        123,
        "token-value",
        {"trigger": "incident.updated"},
    )
    assert http.webhook_slack == (123, "token-value", {"text": "deploy complete"})

    try:
        fluxer.webhook.RequestsWebhookAdapter()
    except RuntimeError:
        pass
    else:
        raise AssertionError("RequestsWebhookAdapter should fail clearly")


class FakeGateway:
    is_connected = True

    def __init__(self) -> None:
        self.calls = []

    async def request_guild_members(self, **kwargs):
        self.calls.append(("members", kwargs))

    async def request_lazy_members(self, **kwargs):
        self.calls.append(("lazy", kwargs))

    async def request_guild_counts(self, guild_ids):
        self.calls.append(("guild_counts", guild_ids))

    async def request_channel_member_counts(self, channel_ids):
        self.calls.append(("channel_counts", channel_ids))

    async def update_presence(self, **kwargs):
        self.calls.append(("presence", kwargs))


async def test_gateway_helpers_and_bulk_events() -> None:
    client: Any = fluxer.Client()
    try:
        await client.request_guild_counts([1])
    except fluxer.GatewayNotConnected:
        pass
    else:
        raise AssertionError("Expected GatewayNotConnected")
    try:
        await client.change_presence(activity=fluxer.Game("offline"))
    except fluxer.GatewayNotConnected:
        pass
    else:
        raise AssertionError("Expected GatewayNotConnected")

    gateway = FakeGateway()
    client._gateway = gateway
    await client.change_presence(
        status="idle",
        activity=fluxer.Streaming(name="build stream", url="https://stream.invalid"),
        afk=True,
        since=123.0,
    )
    assert gateway.calls[-1] == (
        "presence",
        {
            "status": "idle",
            "activity": {
                "name": "build stream",
                "type": 1,
                "url": "https://stream.invalid",
            },
            "afk": True,
            "since": 123.0,
        },
    )
    await client.change_presence(activity="playing tests")
    assert gateway.calls[-1][1]["activity"] == {"name": "playing tests", "type": 0}
    await client.request_guild_members(20, query="a", limit=1, nonce="n")
    await client.request_lazy_members(20, ranges=[[0, 99]])
    await client.request_guild_counts([20])
    await client.request_channel_member_counts([10])
    assert any(call[0] == "members" for call in gateway.calls)
    assert gateway.calls[-1] == ("channel_counts", [10])

    sent = []

    @client.event
    async def on_fluxer_event(raw):
        sent.append((type(raw).__name__, raw.name))

    await client._dispatch(
        "CHANNEL_UPDATE_BULK",
        {
            "channels": [
                {"id": "10", "type": int(fluxer.ChannelType.GUILD_TEXT), "name": "chat"}
            ]
        },
    )
    assert client.get_channel(10).name == "chat"
    assert ("ChannelUpdateBulkEvent", "CHANNEL_UPDATE_BULK") in sent

    guild: Any = fluxer.Guild(id=20, name="Guild")
    client._state.store_guild(guild)
    await client._dispatch(
        "GUILD_ROLE_UPDATE_BULK",
        {"guild_id": "20", "roles": [{"id": "30", "name": "Role"}]},
    )
    assert guild.roles[0].name == "Role"
    assert ("GuildRoleUpdateBulkEvent", "GUILD_ROLE_UPDATE_BULK") in sent

    sent_payloads = []
    real_gateway = Gateway(
        http_client=None,
        token="token",
        intents=fluxer.Intents.default(),
        dispatch=cast(Any, lambda event, data: None),
    )

    async def fake_send(payload):
        sent_payloads.append(payload)

    real_gateway._send = fake_send
    await real_gateway.update_presence(
        status="dnd",
        activity={"name": "serializing", "type": 3},
        afk=False,
        since=None,
    )
    assert sent_payloads[0].op == fluxer.GatewayOpcode.PRESENCE_UPDATE
    assert sent_payloads[0].d == {
        "since": None,
        "activities": [{"name": "serializing", "type": 3}],
        "status": "dnd",
        "afk": False,
    }


async def test_fluxer_only_http_routes() -> None:
    http: Any = HTTPClient("token")
    calls = []

    async def fake_request(route, **kwargs):
        calls.append((route.method, route.path, kwargs))
        if route.path == "/users/@me/scheduled-messages":
            return []
        if route.path == "/users/@me/relationships":
            return []
        if route.path == "/users/@me/applications":
            return []
        if route.path == "/oauth2/applications/@me":
            return {
                "id": "99",
                "name": "Bot App",
                "redirect_uris": [],
                "bot_public": True,
                "bot_require_code_grant": False,
            }
        if route.path == "/oauth2/applications/{id}":
            return {
                "id": "100",
                "name": "Fetched App",
                "redirect_uris": [],
                "bot_public": False,
                "bot_require_code_grant": True,
            }
        if route.path == "/users/@me/gifts":
            return []
        if route.path == "/gifts/{code}":
            return {
                "code": "gift",
                "duration_type": "months",
                "duration_quantity": 1,
                "redeemed": False,
            }
        if route.path == "/guilds/{guild_id}/bans":
            return []
        if route.path == "/guilds/{guild_id}/members":
            return []
        if route.path == "/guilds/{guild_id}/members-search":
            return {"members": []}
        if route.path == "/guilds/{guild_id}/members/@me":
            return {
                "guild_id": "20",
                "user": {"id": "42", "username": "me"},
                "nick": kwargs.get("json", {}).get("nick", "me"),
                "roles": [],
            }
        if route.path == "/guilds/{guild_id}/members/{user_id}":
            return {
                "guild_id": "20",
                "user": {"id": "42", "username": "member"},
                "nick": kwargs.get("json", {}).get("nick", "member"),
                "roles": kwargs.get("json", {}).get("roles", []),
            }
        if route.path == "/guilds/{guild_id}/channels" and route.method == "GET":
            return []
        if route.path == "/guilds/{guild_id}/channels" and route.method == "POST":
            return {
                "id": "10",
                "guild_id": "20",
                "name": kwargs["json"]["name"],
                "type": kwargs["json"]["type"],
            }
        if route.path == "/channels/{channel_id}" and route.method == "PATCH":
            return {
                "id": "10",
                "guild_id": "20",
                "name": kwargs["json"].get("name", "edited"),
                "type": kwargs["json"].get("type", fluxer.ChannelType.GUILD_TEXT),
            }
        if route.path == "/guilds/{guild_id}/roles" and route.method == "GET":
            return []
        if route.path == "/guilds/{guild_id}/roles" and route.method == "PATCH":
            return [
                {
                    "id": "30",
                    "name": "Role",
                    "position": 3,
                    "permissions": "0",
                    "hoist": False,
                    "mentionable": False,
                }
            ]
        if route.path == "/packs":
            return {
                "emoji": {
                    "installed_limit": 50,
                    "created_limit": 10,
                    "installed": [],
                    "created": [],
                },
                "sticker": {
                    "installed_limit": 50,
                    "created_limit": 10,
                    "installed": [],
                    "created": [],
                },
            }
        if route.path == "/packs/{pack_id}/invites" and route.method == "GET":
            return []
        if route.path == "/packs/emojis/{pack_id}" and route.method == "GET":
            return []
        if route.path == "/packs/stickers/{pack_id}" and route.method == "GET":
            return []
        if route.path == "/users/@me/entrance-sounds" and route.method == "GET":
            return {"sounds": [], "selections": []}
        if route.path == "/users/@me/themes":
            return {"id": "abcdef1234567890"}
        if route.path == "/users/@me/memes" and route.method == "GET":
            return {"memes": []}
        if route.path == "/users/@me/saved-messages":
            return {"saved_messages": []}
        if route.path == "/users/@me/mentions":
            return {"messages": []}
        if route.path == "/search/messages":
            return {"messages": [], "total": 0}
        if route.path == "/channels/{channel_id}/messages/pins":
            return {"pins": []}
        return {"id": "scheduled", "status": "pending"}

    http.request = fake_request
    await http.get_saved_messages(limit=2)
    await http.save_message(500, channel_id=10)
    await http.unsave_message(500)
    await http.schedule_message(
        10, scheduled_local_at="2026-01-01T09:00:00", timezone="UTC", content="later"
    )
    await http.get_scheduled_messages()
    await http.update_scheduled_message("scheduled", content="changed")
    await http.cancel_scheduled_message("scheduled")
    await http.get_mentions(limit=1, everyone=True)
    await http.mark_mentions_read([500])
    await http.ack_read_states(
        [{"id": "10", "last_message_id": "500", "mention_count": 0}]
    )
    await http.ack_read_states_bulk(
        [{"id": "10", "last_message_id": "500", "mention_count": 0}]
    )
    await http.bulk_delete_my_messages(reason="cleanup")
    await http.bulk_delete_my_messages_in_guild(20, reason="cleanup")
    await http.request_bulk_message_deletion(password="pw")
    await http.cancel_bulk_message_deletion()
    await http.resolve_gif_urls(["https://example.invalid/a.gif"])
    await http.get_relationships()
    await http.bulk_ignore_friend_requests(user_ids=["42"])
    await http.update_relationship_nickname(42, "pal")
    await http.list_discovery_categories()
    await http.search_discovery_guilds(query="flux", limit=1)
    await http.join_discovery_guild(20)
    await http.get_guild_discovery_status(20)
    await http.apply_for_discovery(20, description="hi")
    await http.edit_discovery_application(20, description="new")
    await http.withdraw_discovery_application(20)
    await http.get_guild_vanity_url(20)
    await http.update_guild_vanity_url(20, "cool")
    await http.bulk_create_guild_emojis(20, [{"name": "wave", "image": "data"}])
    await http.clone_guild_emoji(20, emoji_id="1", name="wave")
    await http.bulk_create_guild_stickers(
        20, [{"name": "wave", "description": "hi", "tags": ["wave"], "image": "data"}]
    )
    await http.clone_guild_sticker(20, sticker_id="2", name="wave")
    await http.transfer_guild_ownership(20, 42, password="pw")
    await http.list_auth_sessions()
    await http.logout_auth_sessions(password="pw")
    await http.get_mfa_state()
    await http.list_webauthn_credentials()
    await http.get_user_settings()
    await http.update_user_settings(theme="dark")
    await http.get_user_applications()
    await http.get_oauth_applications_me()
    await http.get_oauth_application(100)
    await http.get_gift_code("gift")
    await http.redeem_gift_code("gift")
    await http.get_user_gifts()
    await http.list_user_packs()
    await http.create_pack("emoji", name="Faces", description="emoji pack")
    await http.update_pack(600, name="Better")
    await http.delete_pack(600)
    await http.install_pack(600)
    await http.uninstall_pack(600)
    await http.list_pack_invites(600)
    await http.create_pack_invite(600, max_uses=1)
    await http.list_pack_emojis(600)
    await http.create_pack_emoji(600, name="wave", image="data")
    await http.bulk_create_pack_emojis(600, [{"name": "wave", "image": "data"}])
    await http.update_pack_emoji(600, 700, name="new")
    await http.delete_pack_emoji(600, 700, purge=True)
    await http.list_pack_stickers(600)
    await http.create_pack_sticker(
        600, name="sticker", description="hi", tags=["hi"], image="data"
    )
    await http.bulk_create_pack_stickers(
        600,
        [{"name": "sticker", "description": "hi", "tags": ["hi"], "image": "data"}],
    )
    await http.update_pack_sticker(600, 800, name="new")
    await http.delete_pack_sticker(600, 800, purge=False)
    await http.get_entrance_sound_library()
    await http.upload_entrance_sound(name="Hi", audio="data")
    await http.rename_entrance_sound(900, name="Bye")
    await http.delete_entrance_sound(900)
    await http.set_entrance_sound_selection("global", 900)
    await http.play_entrance_sound(10, 900)
    await http.create_theme("body{}")
    await http.get_guild_notification_settings(20)
    await http.update_guild_notification_settings(20, muted=True)
    await http.get_pinned_dms()
    await http.get_user_connections()
    await http.get_authorized_ips()
    await http.request_data_harvest(password="pw")
    await http.get_call_eligibility(10)
    await http.update_call_region(10, "us-east")
    await http.ring_call_recipients(10, [42])
    await http.stop_ringing_call_recipients(10, [42])
    await http.end_call(10)
    await http.list_rtc_regions(10)
    await http.get_channel_slowmode_state(10)
    await http.get_voice_debug_logging_status(10)
    await http.set_voice_debug_logging_status(10, True)
    await http.upload_voice_debug_logging_events(10, [{"name": "debug"}])
    await http.voice_presence_heartbeat(10, active=True)
    await http.get_group_dm_recipient_permissions(10, 42)
    await http.get_favorite_memes()
    await http.create_meme_from_url("https://example.invalid/meme.png", name="meme")
    await http.search_messages(content="hello", channel_ids=["10"])
    await http.get_current_user_guilds(limit=2, before=99, with_counts=True)
    await http.create_guild(name="New Guild", preferred_locale="en-US")
    await http.modify_guild(20, name="Renamed")
    await http.leave_guild(20)
    await http.delete_guild(20)
    await http.get_guild_channels(20)
    await http.create_guild_channel(
        20, name="chat", type=fluxer.ChannelType.GUILD_TEXT, rate_limit_per_user=5
    )
    await http.update_guild_channel_positions(20, [{"id": "10", "position": 2}])
    await http.modify_channel(10, name="renamed", rate_limit_per_user=10)
    await http.edit_channel_permissions(10, 30, allow=2048, deny=65536, type=0)
    await http.delete_channel_permissions(10, 30)
    await http.delete_channel(10, silent=True, delete_messages=False)
    await http.get_pinned_messages(10, limit=1, before="2026-01-02T00:00:00+00:00")
    await http.pin_message(10, 300)
    await http.unpin_message(10, 300)
    await http.acknowledge_pins(10)
    await http.get_guild_bans(20)
    await http.get_guild_member(20, 42)
    await http.get_current_guild_member(20)
    await http.get_guild_members(20, limit=2, after=41)
    await http.search_guild_members(20, query="a", role_ids=[30], limit=1)
    await http.modify_current_guild_member(20, nick="me", bio="bio")
    await http.modify_guild_member(
        20,
        42,
        nick="member",
        roles=[30],
        avatar="data",
        timeout_reason="because",
    )
    await http.add_guild_member_role(20, 42, 30, reason="grant")
    await http.remove_guild_member_role(20, 42, 30, reason="revoke")
    await http.get_guild_roles(20)
    await http.update_guild_role_positions(20, [{"id": "30", "position": 3}])
    await http.update_role_hoist_positions(20, [{"id": "30", "hoist_position": 2}])
    await http.reset_role_hoist_positions(20)
    await http.request_message_attachment_uploads(
        10,
        [
            {
                "id": 0,
                "filename": "hello.txt",
                "file_size": 5,
                "content_type": "text/plain",
            }
        ],
    )
    await http.complete_multipart_message_attachment_uploads(
        10,
        [{"upload_filename": "uploads/big.bin", "upload_id": "multi"}],
    )
    await http.delete_message_attachment(10, 500, 900)
    await http.add_group_dm_recipient(10, 42)
    await http.remove_group_dm_recipient(
        10,
        42,
        silent=True,
        delete_messages=True,
        password="pw",
    )
    await http.execute_github_webhook(123, "token", {"action": "opened"})
    await http.execute_instatus_webhook(123, "token", {"trigger": "incident.updated"})
    await http.execute_slack_webhook(123, "token", {"text": "deploy complete"})

    assert (
        "POST",
        "/users/@me/saved-messages",
        {"json": {"message_id": "500", "channel_id": "10"}},
    ) in calls
    assert any(
        call[0] == "POST" and call[1] == "/channels/{channel_id}/messages/schedule"
        for call in calls
    )
    assert any(call[0] == "POST" and call[1] == "/read-states/ack" for call in calls)
    assert any(
        call[0] == "POST" and call[1] == "/read-states/ack-bulk" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/users/@me/favorite-gifs/resolve"
        for call in calls
    )
    assert any(call[0] == "GET" and call[1] == "/discovery/guilds" for call in calls)
    assert any(
        call[0] == "PATCH" and call[1] == "/guilds/{guild_id}/vanity-url"
        for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/guilds/{guild_id}/emojis/bulk"
        for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/guilds/{guild_id}/transfer-ownership"
        for call in calls
    )
    assert any(call[0] == "GET" and call[1] == "/auth/sessions" for call in calls)
    assert any(call[0] == "GET" and call[1] == "/users/@me/settings" for call in calls)
    assert any(
        call[0] == "GET" and call[1] == "/users/@me/applications" for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/oauth2/applications/@me" for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/oauth2/applications/{id}" for call in calls
    )
    assert any(call[0] == "GET" and call[1] == "/gifts/{code}" for call in calls)
    assert any(
        call[0] == "POST" and call[1] == "/gifts/{code}/redeem" for call in calls
    )
    assert any(call[0] == "GET" and call[1] == "/users/@me/gifts" for call in calls)
    assert any(
        call[0] == "GET" and call[1] == "/guilds/{guild_id}/members/{user_id}"
        for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/guilds/{guild_id}/members/@me"
        for call in calls
    )
    assert any(
        call[0] == "GET"
        and call[1] == "/guilds/{guild_id}/members"
        and call[2]["params"] == {"limit": 2, "after": 41}
        for call in calls
    )
    assert any(
        call[0] == "POST"
        and call[1] == "/guilds/{guild_id}/members-search"
        and call[2]["json"] == {"query": "a", "limit": 1, "role_ids": ["30"]}
        for call in calls
    )
    assert any(
        call[0] == "PATCH"
        and call[1] == "/guilds/{guild_id}/members/@me"
        and call[2]["json"] == {"nick": "me", "bio": "bio"}
        for call in calls
    )
    assert any(
        call[0] == "PATCH"
        and call[1] == "/guilds/{guild_id}/members/{user_id}"
        and call[2]["json"]
        == {
            "nick": "member",
            "avatar": "data",
            "timeout_reason": "because",
            "roles": ["30"],
        }
        for call in calls
    )
    assert any(
        call[0] == "PUT"
        and call[1] == "/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
        and call[2]["reason"] == "grant"
        for call in calls
    )
    assert any(
        call[0] == "DELETE"
        and call[1] == "/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
        and call[2]["reason"] == "revoke"
        for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/guilds/{guild_id}/channels" for call in calls
    )
    assert any(
        call[0] == "POST"
        and call[1] == "/guilds/{guild_id}/channels"
        and call[2]["json"]["rate_limit_per_user"] == 5
        for call in calls
    )
    assert any(
        call[0] == "PATCH"
        and call[1] == "/guilds/{guild_id}/channels"
        and call[2]["json"] == [{"id": "10", "position": 2}]
        for call in calls
    )
    assert any(
        call[0] == "PATCH"
        and call[1] == "/channels/{channel_id}"
        and call[2]["json"]["name"] == "renamed"
        and call[2]["json"]["rate_limit_per_user"] == 10
        for call in calls
    )
    assert any(
        call[0] == "PUT"
        and call[1] == "/channels/{channel_id}/permissions/{overwrite_id}"
        and call[2]["json"] == {"type": 0, "allow": "2048", "deny": "65536"}
        for call in calls
    )
    assert any(
        call[0] == "DELETE"
        and call[1] == "/channels/{channel_id}/permissions/{overwrite_id}"
        for call in calls
    )
    assert any(
        call[0] == "DELETE"
        and call[1] == "/channels/{channel_id}"
        and call[2]["params"] == {"silent": "true", "delete_messages": "false"}
        for call in calls
    )
    assert any(call[0] == "GET" and call[1] == "/packs" for call in calls)
    assert any(call[0] == "POST" and call[1] == "/packs/{pack_type}" for call in calls)
    assert any(call[0] == "PATCH" and call[1] == "/packs/{pack_id}" for call in calls)
    assert any(call[0] == "DELETE" and call[1] == "/packs/{pack_id}" for call in calls)
    assert any(
        call[0] == "POST" and call[1] == "/packs/{pack_id}/install" for call in calls
    )
    assert any(
        call[0] == "DELETE" and call[1] == "/packs/{pack_id}/install" for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/packs/{pack_id}/invites" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/packs/{pack_id}/invites" for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/packs/emojis/{pack_id}" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/packs/emojis/{pack_id}" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/packs/emojis/{pack_id}/bulk"
        for call in calls
    )
    assert any(
        call[0] == "PATCH" and call[1] == "/packs/emojis/{pack_id}/{emoji_id}"
        for call in calls
    )
    assert any(
        call[0] == "DELETE"
        and call[1] == "/packs/emojis/{pack_id}/{emoji_id}"
        and call[2]["params"] == {"purge": "true"}
        for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/packs/stickers/{pack_id}" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/packs/stickers/{pack_id}" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/packs/stickers/{pack_id}/bulk"
        for call in calls
    )
    assert any(
        call[0] == "PATCH" and call[1] == "/packs/stickers/{pack_id}/{sticker_id}"
        for call in calls
    )
    assert any(
        call[0] == "DELETE"
        and call[1] == "/packs/stickers/{pack_id}/{sticker_id}"
        and call[2]["params"] == {"purge": "false"}
        for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/users/@me/entrance-sounds" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/users/@me/entrance-sounds" for call in calls
    )
    assert any(
        call[0] == "PATCH" and call[1] == "/users/@me/entrance-sounds/{sound_id}"
        for call in calls
    )
    assert any(
        call[0] == "DELETE" and call[1] == "/users/@me/entrance-sounds/{sound_id}"
        for call in calls
    )
    assert any(
        call[0] == "PUT"
        and call[1] == "/users/@me/entrance-sound-selections"
        and call[2]["json"] == {"scope_id": "global", "sound_id": "900"}
        for call in calls
    )
    assert any(
        call[0] == "POST"
        and call[1] == "/voice/channels/{channel_id}/entrance-sound"
        and call[2]["json"] == {"sound_id": "900"}
        for call in calls
    )
    assert any(call[0] == "POST" and call[1] == "/users/@me/themes" for call in calls)
    assert any(
        call[0] == "GET" and call[1] == "/channels/{channel_id}/call" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/channels/{channel_id}/call/ring"
        for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/channels/{channel_id}/rtc-regions"
        for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/channels/{channel_id}/slowmode"
        for call in calls
    )
    assert any(call[0] == "POST" and call[1] == "/search/messages" for call in calls)
    assert any(call[0] == "GET" and call[1] == "/users/@me/guilds" for call in calls)
    assert any(call[0] == "POST" and call[1] == "/guilds" for call in calls)
    assert any(call[0] == "PATCH" and call[1] == "/guilds/{guild_id}" for call in calls)
    assert any(
        call[0] == "GET"
        and call[1] == "/channels/{channel_id}/messages/pins"
        and call[2]["params"]
        == {
            "limit": 1,
            "before": "2026-01-02T00:00:00+00:00",
        }
        for call in calls
    )
    assert any(
        call[0] == "PUT" and call[1] == "/channels/{channel_id}/pins/{message_id}"
        for call in calls
    )
    assert any(
        call[0] == "DELETE" and call[1] == "/channels/{channel_id}/pins/{message_id}"
        for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/channels/{channel_id}/pins/ack"
        for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/guilds/{guild_id}/bans" for call in calls
    )
    assert any(
        call[0] == "GET" and call[1] == "/guilds/{guild_id}/roles" for call in calls
    )
    assert any(
        call[0] == "PATCH"
        and call[1] == "/guilds/{guild_id}/roles"
        and call[2]["json"] == [{"id": "30", "position": 3}]
        for call in calls
    )
    assert any(
        call[0] == "PATCH"
        and call[1] == "/guilds/{guild_id}/roles/hoist-positions"
        and call[2]["json"] == [{"id": "30", "hoist_position": 2}]
        for call in calls
    )
    assert any(
        call[0] == "DELETE" and call[1] == "/guilds/{guild_id}/roles/hoist-positions"
        for call in calls
    )
    assert any(
        call[0] == "DELETE" and call[1] == "/users/@me/guilds/{guild_id}"
        for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/guilds/{guild_id}/delete" for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/channels/{channel_id}/attachments"
        for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/channels/{channel_id}/attachments/complete"
        for call in calls
    )
    assert any(
        call[0] == "DELETE"
        and call[1]
        == "/channels/{channel_id}/messages/{message_id}/attachments/{attachment_id}"
        for call in calls
    )
    assert any(
        call[0] == "PUT" and call[1] == "/channels/{channel_id}/recipients/{user_id}"
        for call in calls
    )
    assert any(
        call[0] == "DELETE"
        and call[1] == "/channels/{channel_id}/recipients/{user_id}"
        and call[2]["params"] == {"silent": "true", "delete_messages": "true"}
        and call[2]["json"] == {"password": "pw"}
        for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/webhooks/{webhook_id}/{token}/github"
        for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/webhooks/{webhook_id}/{token}/instatus"
        for call in calls
    )
    assert any(
        call[0] == "POST" and call[1] == "/webhooks/{webhook_id}/{token}/slack"
        for call in calls
    )


async def main() -> None:
    await test_command_conversion()
    await test_command_groups_aliases_and_checks()
    await test_cog_injection()
    await test_fluxer_help_commands()
    await test_fluxer_help_customisation()
    await test_message_channel_parity()
    await test_invites_audit_stickers()
    await test_guild_lifecycle_helpers()
    await test_channel_management_helpers()
    await test_guild_roles_and_bans()
    await test_guild_member_helpers()
    await test_attachment_upload_lifecycle()
    await test_group_dm_recipient_helpers()
    await test_client_cache_dispatch()
    await test_fluxer_models_and_client_helpers()
    await test_webhook_parity()
    await test_gateway_helpers_and_bulk_events()
    await test_fluxer_only_http_routes()
    test_gateway_payload()
    test_route_bucket()
    test_model_mapping()
    test_compat_import_surface()
    print("offline fluxer tests passed")


if __name__ == "__main__":
    asyncio.run(main())
