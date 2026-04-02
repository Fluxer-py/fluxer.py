from __future__ import annotations

import asyncio
import functools
from typing import Callable, Coroutine, Any

from fluxer import Context

from .enums import Permissions
from .models.member import GuildMember
from .models.message import Message

EventHandler = Callable[..., Coroutine[Any, Any, None]]


def has_role(
    name: str | None = None, id: int | str | None = None
) -> Callable[[EventHandler], EventHandler]:
    """Restrict a command to users who have a specific role.

    Works with both standalone commands and cog methods. Can be identified
    by role name (str) or role ID (int). Role name matching is case-sensitive.

    Args:
        name: Role name (str) to require.
        id: Role ID (int or str) to require.

    Example:
        @bot.command()
        @fluxer.checks.has_role(name="Moderator")
        async def warn(ctx):
            await ctx.reply("Issuing warning...")

        @bot.command()
        @fluxer.checks.has_role(id=987654321098765432)
        async def secret(ctx):
            await ctx.reply("You found the secret command!")
    """

    def decorator(func: EventHandler) -> EventHandler:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> None:
            # Make this compatible with both standalone commands and cog methods by checking
            # if the first argument is a bot instance (Cog) or a context object (standalone)
            a: list[Any] = list(args)
            ctx: Context = a[1] if a and hasattr(a[0], "bot") else a[0]
            msg: Message = ctx.message

            if msg.guild_id is None:
                await msg.reply("This command can only be used in a server.")
                return

            if name is None and id is None:
                await msg.reply("Invalid role requirement configuration.")
                return

            if msg._http is None:
                raise RuntimeError("HTTPClient is required to check roles")

            member_data = await msg._http.get_guild_member(msg.guild_id, msg.author.id)

            role_id: int | None = None
            if id is not None:
                role_id = int(id)
            elif name is not None:
                roles_data = await msg._http.get_guild_roles(msg.guild_id)
                role_id = next(
                    (int(r["id"]) for r in roles_data if r["name"] == name),
                    None,
                )

            member = GuildMember.from_data(member_data, msg._http)
            authorized = role_id is not None and member.has_role(role_id)

            if not authorized:
                await msg.reply("You don't have permission to use this command.")
                return

            await func(*args, **kwargs)

        for attr in ("__cog_command__", "__cog_command_name__"):
            if hasattr(func, attr):
                setattr(wrapper, attr, getattr(func, attr))

        return wrapper

    return decorator


def has_permission(permission: Permissions) -> Callable[[EventHandler], EventHandler]:
    """Restrict a command to members who have the specified permission(s).

    Guild owners bypass this check unconditionally. Members with the
    ADMINISTRATOR permission also bypass it.

    Args:
        permission: A Permissions flag, or multiple flags combined with |,
                    that the member must have.

    Example:
        @bot.command()
        @fluxer.checks.has_permission(Permissions.KICK_MEMBERS)
        async def kick(ctx):
            await ctx.reply("Kicking...")

        @bot.command()
        @fluxer.checks.has_permission(Permissions.KICK_MEMBERS | Permissions.BAN_MEMBERS)
        async def punish(ctx):
            await ctx.reply("You can kick and ban.")
    """

    def decorator(func: EventHandler) -> EventHandler:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> None:
            # Make this compatible with both standalone commands and cog methods by checking
            # if the first argument is a bot instance (Cog) or a context object (standalone)
            a: list[Any] = list(args)
            ctx: Context = a[1] if a and hasattr(a[0], "bot") else a[0]
            msg: Message = ctx.message

            if msg.guild_id is None:
                await msg.reply("This command can only be used in a server.")
                return

            if msg._http is None:
                raise RuntimeError("HTTPClient is required to check permissions")

            guild_data, member_data, roles_data = await asyncio.gather(
                msg._http.get_guild(msg.guild_id),
                msg._http.get_guild_member(msg.guild_id, msg.author.id),
                msg._http.get_guild_roles(msg.guild_id),
            )

            # If the user is the guild owner, they bypass all permission checks
            if msg.author.id == int(guild_data["owner_id"]):
                await func(*args, **kwargs)
                return

            member_role_ids = {int(r) for r in member_data.get("roles", [])}
            computed = 0
            for role in roles_data:
                role_id = int(role["id"])
                if role_id == msg.guild_id or role_id in member_role_ids:
                    computed |= int(role["permissions"])

            # If a user has admin, they bypass all permission checks
            if computed & Permissions.ADMINISTRATOR:
                await func(*args, **kwargs)
                return

            if (computed & int(permission)) != int(permission):
                await msg.reply("You don't have permission to use this command.")
                return

            await func(*args, **kwargs)

        for attr in ("__cog_command__", "__cog_command_name__"):
            if hasattr(func, attr):
                setattr(wrapper, attr, getattr(func, attr))

        return wrapper

    return decorator
