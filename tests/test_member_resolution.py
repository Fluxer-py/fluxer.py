"""Members stand in for users, and guild authors resolve to members when known."""

from typing import Any, TypeVar
from unittest.mock import AsyncMock

import pytest

import fluxer
from fluxer.errors import NotFound
from fluxer.ext.commands import Context
from fluxer.http import HTTPClient
from fluxer.models.member import GuildMember

T = TypeVar("T")


def _required(value: T | None) -> T:
    assert value is not None
    return value


def guild_payload() -> dict[str, Any]:
    return {
        "id": "1",
        "name": "guild",
        "owner_id": "99",
        "roles": [{"id": "1", "permissions": "1024"}],
        "channels": [{"id": "2", "type": 0, "name": "chat"}],
        "members": [
            {
                "user": {"id": "3", "username": "author", "bot": True},
                "nick": "nick",
                "roles": ["1"],
            }
        ],
    }


def message_payload(**extra: Any) -> dict[str, Any]:
    return {
        "id": "10",
        "channel_id": "2",
        "guild_id": "1",
        "author": {"id": "3", "username": "author", "bot": True},
        "content": "hello",
        "timestamp": "2026-01-01T00:00:00Z",
        **extra,
    }


async def guild_client() -> fluxer.Client:
    client = fluxer.Client()
    client._http = HTTPClient("test", api_url="https://instance.test/v1")
    client._state.http = client._http
    client._http._state = client._state
    await client._dispatch("GUILD_CREATE", guild_payload())
    return client


def test_member_delegates_user_attributes_and_compares_by_id() -> None:
    member = GuildMember.from_data(
        {
            "user": {"id": "3", "username": "author", "bot": True, "avatar": "abc"},
            "avatar": "guild",
            "accent_color": 5,
        },
        guild_id=1,
    )
    user = fluxer.User(id=3, username="other-copy")
    assert member.username == "author" and member.bot is True
    assert member.avatar_hash == "abc" and member.guild_avatar_hash == "guild"
    assert member.accent_color is None and member.guild_accent_color == 5
    assert member == user and user == member
    assert hash(member) == hash(user) and len({member, user}) == 1
    assert member != fluxer.User(id=4)


@pytest.mark.asyncio
async def test_member_send_delegates_to_user(monkeypatch: pytest.MonkeyPatch) -> None:
    member = GuildMember.from_data({"user": {"id": "3"}}, guild_id=1)
    sent = object()
    send = AsyncMock(return_value=sent)
    monkeypatch.setattr(fluxer.User, "send", send)
    assert await member.send("hi") is sent
    send.assert_awaited_once()
    assert send.call_args.args == ("hi",)


@pytest.mark.asyncio
async def test_gateway_author_uses_payload_member_then_cache() -> None:
    client = await guild_client()
    cached = _required(client.get_member(1, 3))

    await client._dispatch("MESSAGE_CREATE", message_payload(member={"nick": "new"}))
    message = _required(client.get_message(10))
    assert message.author is message.member is cached
    assert cached.nick == "new"

    await client._dispatch("MESSAGE_CREATE", message_payload(id="11"))
    message = _required(client.get_message(11))
    assert message.author is message.member is cached
    assert message.author.bot is True
    await client.close()


@pytest.mark.asyncio
async def test_dm_webhook_and_uncached_authors_stay_users() -> None:
    client = await guild_client()
    await client._dispatch(
        "MESSAGE_CREATE",
        message_payload(id="20", guild_id=None, channel_id="50"),
    )
    await client._dispatch("MESSAGE_CREATE", message_payload(id="21", webhook_id="7"))
    await client._dispatch(
        "MESSAGE_CREATE",
        message_payload(id="22", author={"id": "8", "username": "stranger"}),
    )
    for message_id in (20, 21, 22):
        message = _required(client.get_message(message_id))
        assert type(message.author) is fluxer.User
        assert message.member is None
    await client.close()


@pytest.mark.asyncio
async def test_http_snapshot_author_is_an_independent_member_copy() -> None:
    client = await guild_client()
    http = _required(client._http)
    http.get_message = AsyncMock(return_value=message_payload())
    cached = _required(client.get_member(1, 3))
    snapshot = await client.fetch_message("2", "10")
    assert isinstance(snapshot.author, GuildMember)
    assert snapshot.author == cached and snapshot.author is not cached
    assert snapshot.author.user is not cached.user
    snapshot.author.roles.append(99)
    assert 99 not in cached.roles
    await client.close()


@pytest.mark.asyncio
async def test_reaction_add_passes_cached_member() -> None:
    client = await guild_client()
    await client._dispatch("MESSAGE_CREATE", message_payload())
    users: list[Any] = []

    @client.event
    async def on_reaction_add(reaction: Any, user: Any) -> None:
        users.append(user)

    await client._dispatch(
        "MESSAGE_REACTION_ADD",
        {
            "user_id": "3",
            "channel_id": "2",
            "message_id": "10",
            "guild_id": "1",
            "emoji": {"name": "x"},
        },
    )
    assert users == [client.get_member(1, 3)]
    assert users[0] is client.get_member(1, 3)
    await client.close()


def context_for(client: fluxer.Client, message: fluxer.Message) -> Context:
    bot: Any = client
    return Context(bot=bot, message=message)


@pytest.mark.asyncio
async def test_fetch_author_prefers_cache_then_http() -> None:
    client = await guild_client()
    http = _required(client._http)
    await client._dispatch(
        "MESSAGE_CREATE",
        message_payload(author={"id": "8", "username": "uncached"}),
    )
    message = _required(client.get_message(10))
    ctx = context_for(client, message)
    assert type(ctx.author) is fluxer.User

    http.get_guild_member = AsyncMock(
        return_value={"user": {"id": "8", "username": "uncached"}, "nick": "fetched"}
    )
    fetched = await ctx.fetch_author()
    assert isinstance(fetched, GuildMember) and fetched.nick == "fetched"
    assert fetched.guild_id == 1
    assert client.get_member(1, 8) is None  # snapshots never enter the cache
    assert ctx.author is message.author

    http.get_guild_member = AsyncMock(
        side_effect=NotFound(404, "UNKNOWN_MEMBER", "Unknown member")
    )
    assert await ctx.fetch_author() is message.author

    cached = _required(client.get_member(1, 3))
    await client._dispatch("MESSAGE_CREATE", message_payload(id="11"))
    assert (
        await context_for(client, _required(client.get_message(11))).fetch_author()
        is cached
    )
    await client.close()


@pytest.mark.asyncio
async def test_fetch_author_in_dm_returns_user() -> None:
    client = await guild_client()
    http = _required(client._http)
    http.get_guild_member = AsyncMock()
    await client._dispatch(
        "MESSAGE_CREATE", message_payload(guild_id=None, channel_id="50")
    )
    message = _required(client.get_message(10))
    assert await context_for(client, message).fetch_author() is message.author
    http.get_guild_member.assert_not_awaited()
    await client.close()
