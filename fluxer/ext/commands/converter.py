from __future__ import annotations

import inspect
import re
import types
from typing import Any, Literal, Union, get_args, get_origin

from ...models import (
    Channel,
    Emoji,
    Guild,
    GuildMember,
    Message,
    PartialEmoji,
    Role,
    User,
)
from ...colour import Color, Colour
from .errors import (
    BadArgument,
    BadBoolArgument,
    BadColourArgument,
    BadUnionArgument,
    ChannelNotFound,
    EmojiNotFound,
    GuildNotFound,
    MemberNotFound,
    MessageNotFound,
    RoleNotFound,
    UserNotFound,
)

_ID_REGEX = re.compile(r"^(?:<[@#&]!?(?P<mention_id>[0-9]+)>|(?P<id>[0-9]+))$")


def _parse_snowflake(argument: str) -> int:
    match = _ID_REGEX.match(argument.strip())
    if match is None:
        raise ValueError(f"Expected an ID, got {argument!r}")
    return int(match.group("mention_id") or match.group("id"))


class Converter:
    async def convert(self, ctx: Any, argument: str) -> Any:
        return argument


class IDConverter(Converter):
    async def convert(self, ctx: Any, argument: str) -> Any:
        try:
            return _parse_snowflake(argument)
        except ValueError as exc:
            raise BadArgument(f"Expected an ID, got {argument!r}") from exc


class UserConverter(IDConverter):
    async def convert(self, ctx: Any, argument: str) -> User:
        user_id = await super().convert(ctx, argument)
        try:
            return await ctx.bot.fetch_user(str(user_id))
        except Exception as exc:
            raise UserNotFound(argument) from exc


class MemberConverter(IDConverter):
    async def convert(self, ctx: Any, argument: str) -> GuildMember:
        if ctx.guild is None:
            raise BadArgument("Member conversion requires a guild")
        user_id = await super().convert(ctx, argument)
        try:
            return await ctx.guild.fetch_member(user_id)
        except Exception as exc:
            raise MemberNotFound(argument) from exc


class GuildConverter(IDConverter):
    async def convert(self, ctx: Any, argument: str) -> Guild:
        guild_id = await super().convert(ctx, argument)
        cached = ctx.bot.get_guild(guild_id)
        try:
            return cached or await ctx.bot.fetch_guild(str(guild_id))
        except Exception as exc:
            raise GuildNotFound(argument) from exc


class TextChannelConverter(IDConverter):
    async def convert(self, ctx: Any, argument: str) -> Channel:
        channel_id = await super().convert(ctx, argument)
        try:
            return await ctx.bot.fetch_channel(str(channel_id))
        except Exception as exc:
            raise ChannelNotFound(argument) from exc


VoiceChannelConverter = TextChannelConverter
CategoryChannelConverter = TextChannelConverter


class RoleConverter(IDConverter):
    async def convert(self, ctx: Any, argument: str) -> Role:
        role_id = await super().convert(ctx, argument)
        if ctx.guild is None:
            raise BadArgument("Role conversion requires a guild")
        for role in await ctx.guild.fetch_roles():
            if role.id == role_id:
                return role
        raise RoleNotFound(argument)


class MessageConverter(Converter):
    async def convert(self, ctx: Any, argument: str) -> Message:
        try:
            message_id = int(argument)
        except ValueError as exc:
            raise BadArgument(f"Expected a message ID, got {argument!r}") from exc
        try:
            return await ctx.channel.fetch_message(message_id)
        except Exception as exc:
            raise MessageNotFound(argument) from exc


class ColourConverter(Converter):
    async def convert(self, ctx: Any, argument: str) -> Colour:
        try:
            return Colour.from_str(argument)
        except ValueError as exc:
            raise BadColourArgument(argument) from exc


ColorConverter = ColourConverter


class EmojiConverter(IDConverter):
    async def convert(self, ctx: Any, argument: str) -> Emoji:
        emoji_id = await super().convert(ctx, argument)
        if ctx.guild is None:
            raise EmojiNotFound(argument)
        for emoji in await ctx.guild.fetch_emojis():
            if emoji.id == emoji_id:
                return emoji
        raise EmojiNotFound(argument)


class PartialEmojiConverter(Converter):
    async def convert(self, ctx: Any, argument: str) -> PartialEmoji:
        from ...models.reaction import PartialEmoji

        if argument.startswith("<") and argument.endswith(">") and ":" in argument:
            animated = argument.startswith("<a:")
            parts = argument.strip("<>").split(":")
            if len(parts) == 3:
                return PartialEmoji(name=parts[1], id=int(parts[2]), animated=animated)
        return PartialEmoji(name=argument, id=None, animated=False)


class GameConverter(Converter):
    async def convert(self, ctx: Any, argument: str) -> str:
        return argument


class InviteConverter(Converter):
    async def convert(self, ctx: Any, argument: str) -> Any:
        from ...invite import Invite

        if ctx.bot._http is None:
            raise BadArgument("Bot is not bound to an HTTP client")
        data = await ctx.bot._http.get_invite(argument)
        return Invite.from_data(data, ctx.bot._http)


class clean_content(Converter):
    def __init__(
        self, *, escape_markdown: bool = False, remove_markdown: bool = False
    ) -> None:
        self.escape_markdown = escape_markdown
        self.remove_markdown = remove_markdown

    async def convert(self, ctx: Any, argument: str) -> str:
        from ... import utils

        if self.remove_markdown:
            argument = utils.remove_markdown(argument)
        if self.escape_markdown:
            argument = utils.escape_markdown(argument)
        return utils.escape_mentions(argument)


class _Greedy:
    def __init__(self, converter: Any) -> None:
        self.converter = converter


class Greedy:
    def __class_getitem__(cls, converter: Any) -> _Greedy:
        return _Greedy(converter)


async def run_converter(ctx: Any, converter: Any, argument: str) -> Any:
    if isinstance(converter, str):
        converter = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "User": User,
            "GuildMember": GuildMember,
            "Member": GuildMember,
            "Guild": Guild,
            "Channel": Channel,
            "Role": Role,
            "Message": Message,
            "Colour": Colour,
            "Color": Color,
            "Emoji": Emoji,
            "PartialEmoji": PartialEmoji,
        }.get(converter, str)
    if converter is inspect.Parameter.empty or converter is str:
        return argument
    origin = get_origin(converter)
    args = get_args(converter)
    if origin in {Union, types.UnionType}:
        if type(None) in args:
            inner = [arg for arg in args if arg is not type(None)][0]
            try:
                return await run_converter(ctx, inner, argument)
            except BadArgument:
                return None
        errors: list[Exception] = []
        for inner in args:
            try:
                return await run_converter(ctx, inner, argument)
            except BadArgument as exc:
                errors.append(exc)
        raise BadUnionArgument("argument", args, errors)
    if origin is Literal:
        literal_args = args
        converted = argument
        for literal in literal_args:
            try:
                converted = await run_converter(ctx, type(literal), argument)
            except BadArgument:
                continue
            if converted == literal:
                return converted
        raise BadArgument(f"{argument!r} does not match any literal choice")
    if origin is not None and type(None) in args:
        inner = [arg for arg in args if arg is not type(None)][0]
        try:
            return await run_converter(ctx, inner, argument)
        except BadArgument:
            return None
    if converter is bool:
        lowered = argument.lower()
        if lowered in {"yes", "y", "true", "t", "1", "on", "enable"}:
            return True
        if lowered in {"no", "n", "false", "f", "0", "off", "disable"}:
            return False
        raise BadBoolArgument(argument)
    if converter in {int, float}:
        try:
            if converter is int:
                return _parse_snowflake(argument)
            return converter(argument)
        except ValueError as exc:
            raise BadArgument(str(exc)) from exc
    if isinstance(converter, Converter):
        return await converter.convert(ctx, argument)
    if isinstance(converter, type) and issubclass(converter, Converter):
        return await converter().convert(ctx, argument)
    if converter is User:
        return await UserConverter().convert(ctx, argument)
    if converter is GuildMember:
        return await MemberConverter().convert(ctx, argument)
    if converter is Guild:
        return await GuildConverter().convert(ctx, argument)
    if converter is Channel:
        return await TextChannelConverter().convert(ctx, argument)
    if converter is Role:
        return await RoleConverter().convert(ctx, argument)
    if converter in {Colour, Color}:
        return await ColourConverter().convert(ctx, argument)
    if converter is Emoji:
        return await EmojiConverter().convert(ctx, argument)
    if converter is PartialEmoji:
        return await PartialEmojiConverter().convert(ctx, argument)
    try:
        return converter(argument)
    except Exception as exc:
        raise BadArgument(str(exc)) from exc
