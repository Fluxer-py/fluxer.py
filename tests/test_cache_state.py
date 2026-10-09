"""Live cache ownership, protocol updates, retention, and HTTP isolation."""

import asyncio
import gc
import weakref
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, TypeVar, cast
from unittest.mock import AsyncMock, patch

import pytest

import fluxer
from fluxer.http import HTTPClient


T = TypeVar("T")


def _required(value: T | None) -> T:
    assert value is not None
    return value


def guild_payload() -> dict[str, Any]:
    return {
        "id": "1",
        "name": "guild",
        "owner_id": "99",
        "member_count": 2,
        "roles": [
            {"id": "1", "permissions": "1024"},
            {"id": "4", "permissions": "2048"},
        ],
        "channels": [{"id": "2", "type": 0, "name": "chat"}],
        "members": [
            {"user": {"id": "3", "username": "author"}, "nick": "old", "roles": ["4"]}
        ],
    }


def message_payload(message_id: int = 10, **extra: Any) -> dict[str, Any]:
    return {
        "id": str(message_id),
        "channel_id": "2",
        "guild_id": "1",
        "author": {"id": "3", "username": "author"},
        "content": "hello",
        "timestamp": "2026-01-01T00:00:00Z",
        **extra,
    }


@pytest.mark.asyncio
async def test_entity_identity_views_updates_and_removal() -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", guild_payload())
    guild = _required(client.get_guild(1))
    channel, member, role = (
        _required(guild.get_channel(2)),
        _required(guild.get_member(3)),
        _required(guild.get_role(4)),
    )
    view = guild.members
    with pytest.raises(AttributeError):
        getattr(view, "append")(member)
    with pytest.raises(AttributeError):
        guild.members = []
    assert view[0] is member and list(view[:1]) == [member]
    await client._dispatch("MESSAGE_CREATE", message_payload(member={"roles": ["4"]}))
    message = _required(client.get_message(10))
    assert message.author is message.member is member
    await client._dispatch(
        "GUILD_MEMBER_UPDATE",
        {"guild_id": "1", "user": {"id": "3", "username": "new"}, "nick": "new"},
    )
    await client._dispatch(
        "CHANNEL_UPDATE", {"guild_id": "1", "id": "2", "type": 0, "name": "renamed"}
    )
    await client._dispatch(
        "GUILD_ROLE_UPDATE", {"guild_id": "1", "role": {"id": "4", "name": "renamed"}}
    )
    await client._dispatch("GUILD_UPDATE", {"id": "1", "name": "renamed"})
    assert client.get_guild(1) is guild
    assert guild.members[0] is client.get_member(1, 3) is member
    assert member.nick == member.user.username == "new"
    assert message.author.username == "new"
    assert channel is message.channel is guild.channels[0] is client.get_channel(2)
    assert channel.name == role.name == guild.name == "renamed"
    await client._dispatch(
        "GUILD_MEMBER_REMOVE", {"guild_id": "1", "user": {"id": "3"}}
    )
    assert not view and client.get_member(1, 3) is None
    await client._dispatch("CHANNEL_DELETE", {"id": "2"})
    assert message.channel is None and not guild.channels
    assert client.get_message(10) is None
    assert not client._state._channel_messages and not client._state._guild_messages
    await client.close()


@pytest.mark.asyncio
async def test_disabled_member_retention_and_weak_users() -> None:
    client = fluxer.Client(cache_members=False, max_messages=0)
    await client._dispatch("GUILD_CREATE", guild_payload())
    assert not _required(client.get_guild(1)).members
    assert not client._state.members
    assert not client._users
    seen = []
    client.add_listener(
        lambda_message := AsyncMock(side_effect=seen.append), "on_message"
    )
    await client._dispatch(
        "MESSAGE_CREATE", message_payload(member={"nick": "ephemeral"})
    )
    assert seen[0].member.nick == "ephemeral"
    assert not client.cached_messages
    assert not _required(client.get_guild(1)).members
    del lambda_message
    user = client._state.store_user({"id": "80", "username": "temporary"})
    reference = weakref.ref(user)
    del user
    gc.collect()
    assert reference() is None and 80 not in client._users
    await client.close()


@pytest.mark.asyncio
async def test_ready_id_only_hydration_resume_and_close() -> None:
    client = fluxer.Client()
    payload = guild_payload()
    payload["members"][0]["user"] = {"id": "3"}
    await client._dispatch(
        "READY",
        {
            "user": {"id": "99", "username": "self", "bot": True},
            "users": [{"id": "3", "username": "hydrated", "avatar": "avatar"}],
            "guilds": [payload],
        },
    )
    member = _required(client.get_member(1, 3))
    assert member.user.username == "hydrated"
    await client._dispatch(
        "GUILD_MEMBER_UPDATE", {"guild_id": "1", "user": {"id": "3"}, "nick": None}
    )
    assert member.user.username == "hydrated"
    assert member.user.avatar_hash == "avatar"
    await client._dispatch(
        "GUILD_MEMBER_UPDATE",
        {"guild_id": "1", "user": {"id": "3", "username": "renamed", "avatar": None}},
    )
    assert member.user.avatar_hash is None
    guild = _required(client.get_guild(1))
    await client._dispatch("RESUMED", {})
    assert client.get_guild(1) is guild
    await client._dispatch("GUILD_DELETE", {"id": "1", "unavailable": True})
    assert guild.unavailable and client.get_channel(2) is not None
    await client._dispatch("GUILD_CREATE", guild_payload())
    assert client.get_guild(1) is guild and not guild.unavailable
    await client.close()
    assert not client.guilds and not client._users and client.user is None
    assert not client._state.channels


@pytest.mark.asyncio
@pytest.mark.parametrize("bound,expected", [(0, 0), (2, 2), (None, 3)])
async def test_private_channel_limits(bound: int | None, expected: int) -> None:
    client = fluxer.Client(max_private_channels=bound)
    for channel_id in (10, 11, 12):
        await client._dispatch("CHANNEL_CREATE", {"id": str(channel_id), "type": 1})
    assert len(client._state._private_channels) == expected
    if bound == 2:
        assert client.get_channel(10) is None
        client.get_channel(11)
        await client._dispatch("CHANNEL_CREATE", {"id": "13", "type": 1})
        assert client.get_channel(12) is None
        assert client.get_channel(11) is not None
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("bot,expected", [(True, 128), (False, 130)])
async def test_default_private_limit_depends_on_account(
    bot: bool, expected: int
) -> None:
    client = fluxer.Client()
    await client._dispatch(
        "READY",
        {
            "user": {"id": "1", "bot": bot},
            "private_channels": [{"id": str(i + 10), "type": 1} for i in range(130)],
        },
    )
    assert len(client._state._private_channels) == expected
    await client.close()


@pytest.mark.asyncio
async def test_message_eviction_and_guild_cleanup() -> None:
    client = fluxer.Client(max_messages=2)
    await client._dispatch("GUILD_CREATE", guild_payload())
    for message_id in (10, 11, 12):
        await client._dispatch("MESSAGE_CREATE", message_payload(message_id))
    assert client.get_message(10) is None
    assert client._state._channel_messages == {2: {11, 12}}
    assert client._state._guild_messages == {1: {11, 12}}
    before = _required(client.get_message(11))
    await client._dispatch("MESSAGE_UPDATE", message_payload(11, content="edited"))
    assert client.get_message(11) is before and before.content == "edited"
    await client._dispatch("GUILD_DELETE", {"id": "1"})
    assert not client.cached_messages and not client._state.channels
    assert not client._state._channel_messages and not client._state._guild_messages
    await client.close()


@pytest.mark.asyncio
async def test_role_expression_metadata_and_recipient_events() -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", guild_payload())
    guild = _required(client.get_guild(1))
    await client._dispatch(
        "GUILD_ROLE_CREATE", {"guild_id": "1", "role": {"id": "5", "name": "new"}}
    )
    await client._dispatch(
        "GUILD_ROLE_UPDATE_BULK",
        {"guild_id": "1", "roles": [{"id": "5", "name": "changed"}]},
    )
    assert len(guild.roles) == 3 and _required(guild.get_role(5)).name == "changed"
    await client._dispatch("GUILD_ROLE_DELETE", {"guild_id": "1", "role_id": "4"})
    assert guild.get_role(4) is None and not _required(guild.get_member(3)).roles
    for event, key in [
        ("GUILD_EMOJIS_UPDATE", "emojis"),
        ("GUILD_STICKERS_UPDATE", "stickers"),
    ]:
        await client._dispatch(
            event, {"guild_id": "1", key: [{"id": "8", "name": "wave"}]}
        )
        assert getattr(guild, key)[0].id == 8
        await client._dispatch(event, {"guild_id": "1", key: []})
        assert not getattr(guild, key)
    await client._dispatch(
        "GUILD_COUNTS_UPDATE",
        {"counts": [{"guild_id": "1", "member_count": 7, "online_count": 4}]},
    )
    assert (guild.member_count, guild.online_count) == (7, 4)
    await client._dispatch(
        "CHANNEL_PINS_UPDATE", {"channel_id": "2", "last_pin_timestamp": "now"}
    )
    await client._dispatch("MESSAGE_CREATE", message_payload())
    assert _required(guild.get_channel(2)).last_message_id == 10
    assert _required(guild.get_channel(2)).last_pin_timestamp == "now"
    await client._dispatch("CHANNEL_CREATE", {"id": "9", "type": 3})
    await client._dispatch(
        "CHANNEL_RECIPIENT_ADD", {"channel_id": "9", "user": {"id": "3"}}
    )
    assert (
        _required(client.get_channel(9)).recipients[0]
        is _required(guild.get_member(3)).user
    )
    await client._dispatch(
        "CHANNEL_RECIPIENT_REMOVE", {"channel_id": "9", "user": {"id": "3"}}
    )
    assert not _required(client.get_channel(9)).recipients
    await client.close()


@pytest.mark.asyncio
async def test_passive_voice_versions_and_indexes() -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", guild_payload())
    voice = {
        "guild_id": "1",
        "channel_id": "2",
        "user_id": "3",
        "connection_id": "a",
        "version": 10,
    }
    await client._dispatch(
        "PASSIVE_UPDATES",
        {"guild_id": "1", "channels": {"2": "100"}, "voice_states": [voice]},
    )
    await client._dispatch("VOICE_STATE_UPDATE", {**voice, "connection_id": "b"})
    assert _required(client.get_channel(2)).last_message_id == 100
    assert len(client.get_channel_voice_states(2)) == 2
    assert client.get_channel_voice_user_count(2) == 1
    await client._dispatch(
        "VOICE_STATE_UPDATE", {**voice, "channel_id": None, "version": 11}
    )
    await client._dispatch("VOICE_STATE_UPDATE", voice)
    await client._dispatch("VOICE_STATE_UPDATE", {**voice, "version": 11})
    assert len(client.get_guild_voice_states(1)) == 1
    assert client._state._voice_tombstones[(1, 3, "a")] == 11
    await client._dispatch("CHANNEL_DELETE", {"id": "2"})
    assert not client.get_guild_voice_states(1)
    assert not client._state._voice_users and not client._state._voice_channels
    await client.close()


@pytest.mark.asyncio
async def test_live_voice_identity_and_request_expiration_cleanup() -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", guild_payload())
    payload = {
        "guild_id": "1",
        "user_id": "3",
        "channel_id": "2",
        "connection_id": "a",
        "version": 1,
    }
    current = client._store_voice_state(payload)
    moved = client._store_voice_state({**payload, "channel_id": "8", "version": 2})
    assert moved is current and current.channel_id == 8
    assert not client.get_channel_voice_states(2)
    client._state._track_member_request(1, "older", True)
    older = client._state._member_requests[1]
    client._state._track_member_request(1, "newer", True)
    assert older.timer is not None and older.timer.cancelled()
    client._state._cancel_member_request(1, "older")
    assert client._state._member_requests[1].nonce == "newer"
    newer = client._state._member_requests[1]
    client._state._cancel_member_request(1, "newer")
    assert newer.timer is not None and newer.timer.cancelled()
    assert not client._state._member_requests
    await client.close()


@pytest.mark.asyncio
async def test_member_chunks_completeness_and_interruptions() -> None:
    client = fluxer.Client()
    client._gateway = cast(
        Any,
        SimpleNamespace(
            request_guild_members=AsyncMock(), is_connected=True, close=AsyncMock()
        ),
    )
    await client._dispatch("GUILD_CREATE", guild_payload())
    guild = _required(client.get_guild(1))
    assert not guild.member_cache_complete
    with pytest.raises(RuntimeError, match="member cache is incomplete"):
        _required(guild.get_channel(2)).permissions_for(fluxer.User(id=7))
    await client.request_guild_members(1, nonce="full")
    first = {
        "guild_id": "1",
        "nonce": "full",
        "chunk_count": 2,
        "chunk_index": 0,
        "members": [{"user": {"id": "3"}}],
    }
    await client._dispatch("GUILD_MEMBERS_CHUNK", first)
    await client._dispatch("GUILD_MEMBERS_CHUNK", first)
    assert not guild.member_cache_complete
    await client._dispatch(
        "GUILD_MEMBERS_CHUNK",
        {**first, "chunk_index": 1, "members": [{"user": {"id": "6"}}]},
    )
    assert guild.member_cache_complete
    assert _required(guild.get_channel(2)).permissions_for(fluxer.User(id=7)) == 0
    await client.request_guild_members(1, query="a", nonce="partial")
    await client._dispatch(
        "GUILD_MEMBERS_CHUNK", {**first, "nonce": "partial", "chunk_count": 1}
    )
    assert not guild.member_cache_complete
    await client.request_guild_members(1, nonce="lost")
    client._state._interrupt()
    await client._dispatch(
        "GUILD_MEMBERS_CHUNK", {**first, "nonce": "lost", "chunk_count": 1}
    )
    assert not guild.member_cache_complete and not client._state._member_requests
    await client.close()


@pytest.mark.asyncio
async def test_lazy_list_sync_is_not_membership_removal() -> None:
    client = fluxer.Client()
    client._gateway = cast(
        Any,
        SimpleNamespace(
            request_lazy_members=AsyncMock(), is_connected=True, close=AsyncMock()
        ),
    )
    await client._dispatch("GUILD_CREATE", guild_payload())
    await client.request_lazy_members(1, channel_id=2, ranges=[[0, 2]])
    payload = {
        "guild_id": "1",
        "id": "2",
        "ops": [
            {
                "op": "SYNC",
                "range": [0, 2],
                "items": [{"member": {"user": {"id": "6"}}}],
            }
        ],
    }
    await client._dispatch("GUILD_MEMBER_LIST_UPDATE", payload)
    assert client._state._member_lists[1] == {0: 6}
    await client._dispatch(
        "GUILD_MEMBER_LIST_UPDATE",
        {
            **payload,
            "ops": [
                {"op": "UNKNOWN", "range": [0, 2]},
                {"op": "SYNC", "range": [-1, 200]},
            ],
        },
    )
    assert client._state._member_lists[1] == {0: 6}
    await client._dispatch(
        "GUILD_MEMBER_LIST_UPDATE",
        {**payload, "ops": [{"op": "SYNC", "range": [0, 2], "items": []}]},
    )
    assert client._state._member_lists[1] == {}
    assert client.get_member(1, 6) is not None
    assert not _required(client.get_guild(1)).member_cache_complete
    await client.close()


@pytest.mark.asyncio
async def test_http_snapshots_and_late_response_leave_live_state_intact() -> None:
    client = fluxer.Client()
    http = HTTPClient("test", api_url="https://instance.test/v1")
    client._http = http
    await client._dispatch("GUILD_CREATE", guild_payload())
    payload = message_payload(embeds=[{"fields": [{"name": "field", "value": "old"}]}])
    await client._dispatch("MESSAGE_CREATE", payload)
    http.get_message = AsyncMock(return_value=payload)
    snapshot = await client.fetch_message("2", "10")
    live = _required(client.get_message(10))
    assert snapshot is not live and snapshot.author is not live.author
    snapshot.embeds[0].fields[0].value = "changed"
    assert live.embeds[0].fields[0].value == "old"
    gate = asyncio.Event()

    async def delayed(*args: Any) -> dict[str, Any]:
        await gate.wait()
        return {"id": "2", "guild_id": "1", "type": 0, "name": "old response"}

    http.get_channel = cast(Any, delayed)
    pending = asyncio.create_task(client.fetch_channel("2"))
    await client._dispatch(
        "CHANNEL_UPDATE", {"id": "2", "guild_id": "1", "type": 0, "name": "new event"}
    )
    gate.set()
    fetched = await pending
    assert (
        fetched.name == "old response"
        and _required(client.get_channel(2)).name == "new event"
    )
    assert fetched.guild is client.get_guild(1)
    http.get_guild = AsyncMock(return_value={"id": "1", "name": "http"})
    snapshot_guild = await client.fetch_guild("1")
    assert not snapshot_guild.channels
    assert _required(client.get_guild(1)).channels
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("max_messages", [0, 2])
async def test_commands_share_message_without_blocking_cache(max_messages: int) -> None:
    bot = fluxer.Bot(command_prefix="!", max_messages=max_messages)
    await bot._dispatch("GUILD_CREATE", guild_payload())
    started, release = asyncio.Event(), asyncio.Event()
    observed, invoked = [], []

    @bot.event
    async def on_message(message: fluxer.Message) -> None:
        observed.append(message)

    @bot.command()
    async def slow(ctx: Any) -> None:
        invoked.append(ctx.message)
        started.set()
        await release.wait()

    with patch.object(
        fluxer.Message, "from_data", wraps=fluxer.Message.from_data
    ) as parse:
        await asyncio.wait_for(
            bot._dispatch("MESSAGE_CREATE", message_payload(content="!slow")), 1
        )
        await asyncio.wait_for(started.wait(), 1)
        assert parse.call_count == 1
    await bot._dispatch(
        "CHANNEL_UPDATE",
        {"id": "2", "guild_id": "1", "type": 0, "name": "while blocked"},
    )
    assert _required(bot.get_channel(2)).name == "while blocked"
    assert observed[0] is invoked[0]
    assert (bot.get_message(10) is observed[0]) == bool(max_messages)
    tasks = tuple(bot._handler_tasks)
    await bot.close()
    assert all(task.done() for task in tasks)


@pytest.mark.asyncio
async def test_batched_reactions_preserve_animation_and_original_data() -> None:
    client = fluxer.Client()
    await client._dispatch("MESSAGE_CREATE", message_payload())
    payload = {
        "channel_id": "2",
        "message_id": "10",
        "reactions": [
            {"user_id": "3", "emoji": {"id": "8", "name": "wave", "animated": True}},
            {"user_id": "4", "emoji": {"id": "8", "name": "wave"}},
        ],
    }
    original = deepcopy(payload)
    data_seen, individual_data = [], []
    client.add_listener(
        AsyncMock(side_effect=data_seen.append), "on_message_reaction_add_many_data"
    )
    client.add_listener(
        AsyncMock(side_effect=individual_data.append), "on_message_reaction_add_data"
    )
    await client._dispatch("MESSAGE_REACTION_ADD_MANY", payload)
    reactions = _required(client.get_message(10)).reactions
    assert len(reactions) == 1 and reactions[0].count == 2
    assert reactions[0].emoji.animated
    assert data_seen == [payload] and data_seen[0] is payload
    assert not individual_data and payload == original
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event", ["GUILD_SYNC", "GUILD_MEMBER_ADD", "GUILD_MEMBER_REMOVE", "RATE_LIMITED"]
)
async def test_roster_request_invalidated_by_intervening_changes(event: str) -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", guild_payload())
    client._state._track_member_request(1, "request", True)
    payloads = {
        "GUILD_SYNC": guild_payload(),
        "GUILD_MEMBER_ADD": {"guild_id": "1", "user": {"id": "6"}},
        "GUILD_MEMBER_REMOVE": {"guild_id": "1", "user": {"id": "3"}},
        "RATE_LIMITED": {"meta": {"guild_id": "1", "nonce": "request"}},
    }
    await client._dispatch(event, payloads[event])
    assert not client._state._member_requests
    assert not _required(client.get_guild(1)).member_cache_complete
    await client.close()


@pytest.mark.asyncio
async def test_roster_timeout_missing_chunks_and_count_mismatch() -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", guild_payload())
    guild = _required(client.get_guild(1))
    client._state._track_member_request(1, "request", True)
    chunk = {
        "guild_id": "1",
        "nonce": "request",
        "chunk_index": 0,
        "chunk_count": 1,
        "members": [{"user": {"id": "3"}}],
    }
    await client._dispatch("GUILD_MEMBERS_CHUNK", chunk)
    assert not guild.member_cache_complete
    client._state._track_member_request(1, "request", True)
    client._state._member_requests[1].started -= 61
    await client._dispatch("GUILD_MEMBERS_CHUNK", chunk)
    assert not guild.member_cache_complete and not client._state._member_requests
    client._state._track_member_request(1, "request", True)
    await client._dispatch("GUILD_MEMBERS_CHUNK", {**chunk, "chunk_count": 2})
    assert not guild.member_cache_complete
    await client._dispatch("READY", {"user": {"id": "9", "bot": True}})
    assert not client._state._member_requests and not client.guilds
    await client.close()


@pytest.mark.asyncio
async def test_guild_sync_replaces_only_supplied_collections() -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", guild_payload())
    guild = _required(client.get_guild(1))
    member = guild.get_member(3)
    role = guild.get_role(1)
    await client._dispatch(
        "GUILD_SYNC",
        {"id": "1", "channels": [], "roles": [{"id": "1", "permissions": "0"}]},
    )
    assert guild.get_member(3) is member
    assert guild.get_role(1) is role and len(guild.roles) == 1
    assert not guild.channels and client.get_channel(2) is None
    assert not guild.member_cache_complete
    await client.close()


@pytest.mark.asyncio
async def test_model_http_fetch_history_and_search_stay_detached() -> None:
    client = fluxer.Client()
    http = HTTPClient("test", api_url="https://instance.test/v1")
    client._http = http
    await client._dispatch("GUILD_CREATE", guild_payload())
    await client._dispatch("MESSAGE_CREATE", message_payload())
    live = _required(client.get_message(10))
    channel = _required(client.get_channel(2))
    http.get_message = AsyncMock(return_value=message_payload(content="fetched"))
    fetched = await channel.fetch_message(10)
    assert fetched is not live and fetched.channel is channel
    http.get_messages = AsyncMock(return_value=[message_payload(content="history")])
    messages = await channel.fetch_messages()
    assert messages[0] is not live and live.content == "hello"
    http.get_guild_member = AsyncMock(
        return_value={"user": {"id": "3", "username": "http"}, "nick": "http"}
    )
    member = await _required(client.get_guild(1)).fetch_member(3)
    assert member is not client.get_member(1, 3)
    assert _required(client.get_member(1, 3)).user.username == "author"
    from fluxer.fluxer_models import parse_search_response

    results = parse_search_response(
        {"messages": [message_payload(content="search")]}, http
    )
    assert isinstance(results, fluxer.SearchResult)
    assert results.messages[0] is not live
    assert results.messages[0].content == "search" and live.content == "hello"
    await client.close()


@pytest.mark.asyncio
async def test_guild_sync_preserves_voice_identity_and_reconciles_indexes() -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", guild_payload())
    payload = {
        "guild_id": "1",
        "user_id": "3",
        "channel_id": "2",
        "connection_id": "a",
        "version": 1,
    }
    current = client._store_voice_state(payload)
    client._store_voice_state({**payload, "connection_id": "b"})
    await client._dispatch(
        "GUILD_SYNC",
        {"id": "1", "voice_states": [{**payload, "channel_id": "8", "version": 2}]},
    )
    assert client.get_voice_state(1, 3) is current
    assert current.channel_id == 8 and current.version == 2
    assert client.get_channel_voice_states(8) == [current]
    assert not client.get_channel_voice_states(2)
    assert set(client._state.voice_states[1]) == {(3, "a")}
    await client._dispatch("VOICE_STATE_UPDATE", {**payload, "connection_id": "b"})
    assert set(client._state.voice_states[1]) == {(3, "a")}
    await client._dispatch("GUILD_SYNC", {"id": "1", "voice_states": []})
    assert not client._state.voice_states and not client._state._voice_users
    assert not client._state._voice_channels
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("include_user", [False, True])
async def test_member_edit_returns_snapshot_without_replacing_live_user(
    include_user: bool,
) -> None:
    client = fluxer.Client()
    http = HTTPClient("test", api_url="https://instance.test/v1")
    client._http = http
    await client._dispatch("GUILD_CREATE", guild_payload())
    member = _required(client.get_member(1, 3))
    shared_user = member.user
    response: dict[str, Any] = {"nick": "http-old", "roles": ["4"]}
    if include_user:
        response["user"] = {"id": "3", "username": "http-old"}

    async def late_response(*args: Any, **kwargs: Any) -> dict[str, Any]:
        await client._dispatch(
            "GUILD_MEMBER_UPDATE",
            {
                "guild_id": "1",
                "user": {"id": "3", "username": "gateway-new"},
                "nick": "gateway-new",
                "roles": [],
            },
        )
        return response

    http.modify_guild_member = AsyncMock(side_effect=late_response)
    snapshot = await member.edit(nick="requested")
    assert snapshot is not member and snapshot.nick == "http-old"
    assert member.nick == "gateway-new" and member.roles == []
    assert member.user is shared_user is client._users[3]
    assert member.user.username == "gateway-new"
    assert snapshot.user is not shared_user
    snapshot.user.username = "snapshot-only"
    snapshot.user.raw_data["username"] = "snapshot-only"
    snapshot.roles.append(99)
    assert shared_user.username == "gateway-new"
    assert shared_user.raw_data["username"] == "gateway-new"
    assert not member.roles
    assert snapshot._http is http and snapshot.user._http is http
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["gateway", "http"])
async def test_shutdown_releases_cache_even_when_transport_close_fails(
    failure: str,
) -> None:
    client = fluxer.Client()
    gateway = SimpleNamespace(close=AsyncMock())
    http = SimpleNamespace(close=AsyncMock())
    client._gateway = cast(Any, gateway)
    client._http = cast(Any, http)
    await client._dispatch("GUILD_CREATE", guild_payload())
    await client._dispatch("MESSAGE_CREATE", message_payload())
    client._state._track_member_request(1, "pending", True)
    request = client._state._member_requests[1]
    (gateway if failure == "gateway" else http).close.side_effect = RuntimeError(
        failure
    )
    with pytest.raises(RuntimeError, match=failure):
        await client.close()
    assert not client.guilds and not client._state.channels
    assert not client.cached_messages and not client._users
    assert not client._state._member_requests
    assert request.timer is not None and request.timer.cancelled()
    gateway.close.assert_awaited_once()
    http.close.assert_awaited_once()
