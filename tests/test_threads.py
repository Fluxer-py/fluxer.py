"""Thread REST routes, Channel/Message/Guild thread methods and ThreadConverter."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

import fluxer
from fluxer._types import UNSET
from fluxer.ext import commands
from fluxer.http import HTTPClient

THREADS = {"X-Fluxer-Features": "channel_threads"}


def thread_payload(thread_id: str = "40", **extra: Any) -> dict[str, Any]:
    return {
        "id": thread_id,
        "type": 11,
        "guild_id": "1",
        "parent_id": "2",
        "owner_id": "3",
        "name": "thread",
        "thread_metadata": {
            "archived": True,
            "auto_archive_duration": 4320,
            "archive_timestamp": "2026-11-0{}T00:00:00+00:00".format(
                int(thread_id) % 9 + 1
            ),
            "locked": False,
        },
        **extra,
    }


def guild_payload(**extra: Any) -> dict[str, Any]:
    return {
        "id": "1",
        "name": "guild",
        "owner_id": "9",
        "roles": [
            {
                "id": "1",
                "name": "@everyone",
                "permissions": str(
                    int(
                        fluxer.Permissions.VIEW_CHANNEL
                        | fluxer.Permissions.SEND_MESSAGES
                        | fluxer.Permissions.SEND_MESSAGES_IN_THREADS
                    )
                ),
            }
        ],
        "channels": [
            {
                "id": "2",
                "type": 0,
                "name": "chat",
                "permission_overwrites": [
                    {
                        "id": "1",
                        "type": 0,
                        "allow": "0",
                        "deny": str(int(fluxer.Permissions.SEND_MESSAGES)),
                    }
                ],
            }
        ],
        "members": [{"user": {"id": "3", "username": "author"}, "roles": []}],
        **extra,
    }


class FakeHTTP:
    """Records thread calls and returns canned payloads."""

    _state = None

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.pages: list[Any] = []
        self.response: Any = None

    def __getattr__(self, name: str) -> Any:
        async def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            if self.pages:
                return self.pages.pop(0)
            return self.response

        return call


def http_client() -> tuple[HTTPClient, AsyncMock]:
    http = HTTPClient("test", api_url="https://instance.test/v1")
    mock = AsyncMock(return_value={})
    http.request = mock  # type: ignore[method-assign]
    return http, mock


def ready_client() -> fluxer.Client:
    client = fluxer.Client()
    client._state._parse_dispatch(
        "READY",
        {
            "session_id": "s",
            "user": {"id": "99", "username": "bot", "bot": True},
            "guilds": [],
        },
    )
    client._state._parse_dispatch(
        "GUILD_CREATE", guild_payload(threads=[thread_payload("41")])
    )
    return client


# -- HTTP routes -----------------------------------------------------------


@pytest.mark.asyncio
async def test_start_thread_routes_send_documented_bodies() -> None:
    http, mock = http_client()
    await http.start_thread_with_message(
        2, 10, name="t", auto_archive_duration=60, reason="why"
    )
    route = mock.call_args.args[0]
    assert (route.method, route.path) == (
        "POST",
        "/channels/{channel_id}/messages/{message_id}/threads",
    )
    assert mock.call_args.kwargs["json"] == {"name": "t", "auto_archive_duration": 60}
    assert mock.call_args.kwargs["reason"] == "why"
    assert mock.call_args.kwargs["headers"] == THREADS

    await http.start_thread_without_message(
        2, name="t", type=12, invitable=False, rate_limit_per_user=5
    )
    route = mock.call_args.args[0]
    assert route.path == "/channels/{channel_id}/threads"
    assert mock.call_args.kwargs["json"] == {
        "name": "t",
        "rate_limit_per_user": 5,
        "type": 12,
        "invitable": False,
    }


@pytest.mark.asyncio
async def test_start_thread_validates_name_and_duration() -> None:
    http, mock = http_client()
    with pytest.raises(ValueError, match="1 to 100"):
        await http.start_thread_without_message(2, name="", type=11)
    with pytest.raises(ValueError, match="auto_archive_duration"):
        await http.start_thread_with_message(2, 3, name="t", auto_archive_duration=5)
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_thread_member_routes() -> None:
    http, mock = http_client()
    expected = [
        (http.join_thread(2), "PUT", "/channels/{channel_id}/thread-members/@me"),
        (http.leave_thread(2), "DELETE", "/channels/{channel_id}/thread-members/@me"),
        (
            http.add_thread_member(2, 3),
            "PUT",
            "/channels/{channel_id}/thread-members/{user_id}",
        ),
        (
            http.remove_thread_member(2, 3),
            "DELETE",
            "/channels/{channel_id}/thread-members/{user_id}",
        ),
    ]
    for coro, method, path in expected:
        await coro
        route = mock.call_args.args[0]
        assert (route.method, route.path) == (method, path)
        assert mock.call_args.kwargs["headers"] == THREADS

    await http.get_thread_member(2, 3, with_member=True)
    assert mock.call_args.kwargs["params"] == {"with_member": "true"}
    await http.get_thread_members(2, after=7, limit=50)
    assert mock.call_args.kwargs["params"] == {"limit": 50, "after": "7"}
    with pytest.raises(ValueError):
        await http.get_thread_members(2, limit=0)


@pytest.mark.asyncio
async def test_archived_and_active_thread_routes() -> None:
    http, mock = http_client()
    await http.get_active_threads(1)
    assert mock.call_args.args[0].path == "/guilds/{guild_id}/threads/active"
    await http.get_public_archived_threads(2, before="2026-01-01T00:00:00+00:00")
    assert mock.call_args.args[0].path == (
        "/channels/{channel_id}/threads/archived/public"
    )
    assert mock.call_args.kwargs["params"] == {
        "limit": 50,
        "before": "2026-01-01T00:00:00+00:00",
    }
    await http.get_private_archived_threads(2, limit=2)
    assert mock.call_args.args[0].path.endswith("/threads/archived/private")
    await http.get_joined_private_archived_threads(2, before=40)
    assert mock.call_args.args[0].path == (
        "/channels/{channel_id}/users/@me/threads/archived/private"
    )
    assert mock.call_args.kwargs["params"]["before"] == "40"
    with pytest.raises(ValueError, match="2 to 100"):
        await http.get_public_archived_threads(2, limit=1)


@pytest.mark.asyncio
async def test_modify_and_delete_channel_take_reason() -> None:
    http, mock = http_client()
    await http.modify_channel(2, archived=True, reason="done")
    assert mock.call_args.kwargs["json"] == {"archived": True}
    assert mock.call_args.kwargs["reason"] == "done"
    assert "channel_threads" in mock.call_args.kwargs["headers"]["X-Fluxer-Features"]
    await http.delete_channel(2, reason="bye")
    assert mock.call_args.kwargs["reason"] == "bye"


# -- Channel methods -------------------------------------------------------


def bound_channel(**data: Any) -> tuple[fluxer.Channel, FakeHTTP]:
    fake = FakeHTTP()
    payload = {"id": "2", "type": 0, "guild_id": "1", **data}
    return fluxer.Channel.from_data(payload, cast(Any, fake)), fake


@pytest.mark.asyncio
async def test_create_thread_with_and_without_message() -> None:
    channel, fake = bound_channel()
    fake.response = thread_payload("10", member={"join_timestamp": None, "flags": 0})
    thread = await channel.create_thread(name="t", message=SimpleNamespace(id=10))
    name, args, kwargs = fake.calls[-1]
    assert name == "start_thread_with_message" and args == (2, 10)
    assert kwargs["name"] == "t" and "type" not in kwargs
    assert thread.is_thread and thread.id == 10

    fake.response = thread_payload("11", type=12)
    await channel.create_thread(name="p", slowmode_delay=5)
    name, args, kwargs = fake.calls[-1]
    assert name == "start_thread_without_message"
    assert kwargs["type"] == 12 and kwargs["invitable"] is True
    assert kwargs["rate_limit_per_user"] == 5

    await channel.create_thread(name="q", type=fluxer.ChannelType.PUBLIC_THREAD)
    kwargs = fake.calls[-1][2]
    assert kwargs["type"] == 11 and kwargs["invitable"] is UNSET


@pytest.mark.asyncio
async def test_edit_sends_only_passed_fields() -> None:
    channel, fake = bound_channel(**thread_payload())
    fake.response = thread_payload(name="renamed")
    edited = await channel.edit(
        name="renamed", archived=False, slowmode_delay=None, reason="r"
    )
    name, args, kwargs = fake.calls[-1]
    assert name == "modify_channel" and args == (40,)
    assert kwargs == {
        "name": "renamed",
        "topic": UNSET,
        "nsfw": UNSET,
        "reason": "r",
        "rate_limit_per_user": None,
        "archived": False,
    }
    assert edited.name == "renamed"

    await channel.delete(reason="x")
    assert fake.calls[-1] == ("delete_channel", (40,), {"reason": "x"})


@pytest.mark.asyncio
async def test_archived_threads_paginates_with_timestamp_cursor() -> None:
    channel, fake = bound_channel()
    fake.pages = [
        {
            "threads": [thread_payload("43"), thread_payload("42")],
            "members": [{"id": "42", "user_id": "99", "flags": 0}],
            "has_more": True,
        },
        {"threads": [thread_payload("41")], "members": [], "has_more": False},
    ]
    threads = [t async for t in channel.archived_threads(limit=None)]
    assert [t.id for t in threads] == [43, 42, 41]
    assert threads[1].me is not None and threads[0].me is None
    first, second = fake.calls
    assert first[0] == "get_public_archived_threads"
    assert first[2] == {"before": None, "limit": 100}
    assert (
        second[2]["before"]
        == thread_payload("42")["thread_metadata"]["archive_timestamp"]
    )


@pytest.mark.asyncio
async def test_archived_threads_limit_cursor_and_modes() -> None:
    channel, fake = bound_channel()
    fake.response = {
        "threads": [thread_payload("43"), thread_payload("42")],
        "members": [],
        "has_more": True,
    }
    threads = [t async for t in channel.archived_threads(limit=1)]
    assert [t.id for t in threads] == [43]
    assert fake.calls[-1][2]["limit"] == 2

    before = datetime(2026, 1, 1, tzinfo=timezone.utc)
    [t async for t in channel.archived_threads(private=True, limit=1, before=before)]
    assert fake.calls[-1][0] == "get_private_archived_threads"
    assert fake.calls[-1][2]["before"] == "2026-01-01T00:00:00+00:00"

    marker = SimpleNamespace(id=12345)
    [
        t
        async for t in channel.archived_threads(
            private=True, joined=True, limit=1, before=marker
        )
    ]
    assert fake.calls[-1][0] == "get_joined_private_archived_threads"
    assert fake.calls[-1][2]["before"] == "12345"

    with pytest.raises(ValueError, match="private"):
        [t async for t in channel.archived_threads(joined=True)]


@pytest.mark.asyncio
async def test_thread_membership_methods() -> None:
    thread, fake = bound_channel(**thread_payload())
    await thread.join()
    await thread.leave()
    await thread.add_user(SimpleNamespace(id=5))
    await thread.remove_user(6)
    assert [(n, a) for n, a, _ in fake.calls] == [
        ("join_thread", (40,)),
        ("leave_thread", (40,)),
        ("add_thread_member", (40, 5)),
        ("remove_thread_member", (40, 6)),
    ]

    fake.pages = [
        [{"id": "40", "user_id": str(i), "flags": 0} for i in range(1, 101)],
        [{"id": "40", "user_id": "200", "flags": 0}],
    ]
    members = await thread.fetch_members()
    assert len(members) == 101 and members[-1].id == 200
    assert fake.calls[-1][2]["after"] == 100

    fake.response = {
        "id": "40",
        "user_id": "3",
        "flags": 0,
        "member": {"user": {"id": "3", "username": "author"}, "roles": []},
    }
    member = await thread.fetch_member(3)
    assert member.id == 3 and member.thread_id == 40
    assert member.member is not None and member.member.id == 3


@pytest.mark.asyncio
async def test_thread_only_methods_reject_other_channels() -> None:
    channel, fake = bound_channel()
    with pytest.raises(TypeError, match="threads"):
        await channel.join()
    assert fake.calls == []


def test_thread_cache_lookups_and_parent_permissions() -> None:
    client = ready_client()
    guild = client.get_guild(1)
    assert guild is not None
    parent = guild.get_channel(2)
    thread = guild.get_thread(41)
    assert parent is not None and thread is not None
    assert thread.guild is guild
    assert parent.threads == [thread] and parent.get_thread(41) is thread
    assert parent.get_thread(999) is None
    assert thread.owner is not None and thread.owner.id == 3
    assert thread.slowmode_delay == 0

    member = guild.get_member(3)
    assert member is not None
    perms = thread.permissions_for(member)
    assert perms == parent.permissions_for(member)
    assert not perms & fluxer.Permissions.SEND_MESSAGES
    assert perms & fluxer.Permissions.SEND_MESSAGES_IN_THREADS


# -- Message and Guild -----------------------------------------------------


def message_payload(**extra: Any) -> dict[str, Any]:
    return {
        "id": "10",
        "channel_id": "2",
        "guild_id": "1",
        "author": {"id": "3", "username": "author"},
        "content": "hello",
        "timestamp": "2026-01-01T00:00:00Z",
        **extra,
    }


@pytest.mark.asyncio
async def test_message_create_thread_and_thread_property() -> None:
    fake = FakeHTTP()
    fake.response = thread_payload("10")
    message = fluxer.Message.from_data(message_payload(), cast(Any, fake))
    thread = await message.create_thread(name="t", auto_archive_duration=1440)
    name, args, kwargs = fake.calls[-1]
    assert name == "start_thread_with_message" and args == (2, 10)
    assert kwargs["auto_archive_duration"] == 1440
    assert thread.id == 10

    assert message.thread is None
    with_thread = fluxer.Message.from_data(
        message_payload(thread=thread_payload("10"), flags=1 << 5), cast(Any, fake)
    )
    assert with_thread.flags.has_thread
    assert with_thread.thread is not None and with_thread.thread.id == 10

    await message.fetch_thread()
    assert fake.calls[-1][:2] == ("get_channel", (10,))

    partial = fluxer.PartialMessage(channel_id=2, id=10, _http=cast(Any, fake))
    await partial.create_thread(name="p")
    assert fake.calls[-1][1] == (2, 10)

    dm = fluxer.Message.from_data(
        {**message_payload(), "guild_id": None}, cast(Any, fake)
    )
    with pytest.raises(ValueError, match="guild"):
        await dm.create_thread(name="t")


@pytest.mark.asyncio
async def test_guild_active_threads_attaches_own_membership() -> None:
    client = ready_client()
    guild = client.get_guild(1)
    assert guild is not None
    fake = FakeHTTP()
    fake.response = {
        "threads": [thread_payload("50"), thread_payload("51")],
        "members": [{"id": "51", "user_id": "99", "flags": 0}],
    }
    guild._http = cast(Any, fake)
    threads = await guild.active_threads()
    assert [t.id for t in threads] == [50, 51]
    assert threads[1].me is not None and threads[1].me.id == 99
    assert guild.get_thread(50) is None  # not cached


# -- Converter -------------------------------------------------------------


@pytest.mark.asyncio
async def test_thread_converter() -> None:
    client = ready_client()
    guild = client.get_guild(1)
    ctx = SimpleNamespace(guild=guild)
    converter = commands.ThreadConverter()
    assert (await converter.convert(ctx, "41")).id == 41
    assert (await converter.convert(ctx, "<#41>")).id == 41
    assert (await converter.convert(ctx, "thread")).id == 41
    with pytest.raises(commands.ThreadNotFound) as info:
        await converter.convert(ctx, "2")
    assert info.value.argument == "2"
    with pytest.raises(commands.ThreadNotFound):
        await converter.convert(SimpleNamespace(guild=None), "41")
