"""AllowedMentions: payload shape, merging, client defaults and mention_author."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import fluxer
from fluxer._types import UNSET
from fluxer.ext import commands
from fluxer.http import HTTPClient
from fluxer.state import ConnectionState


def message_payload(**extra: Any) -> dict[str, Any]:
    return {
        "id": "100",
        "channel_id": "10",
        "author": {"id": "3", "username": "bot"},
        "content": "hi",
        "timestamp": "2026-01-01T00:00:00Z",
        **extra,
    }


def http_client(default: fluxer.AllowedMentions | None = None) -> HTTPClient:
    http = HTTPClient("test", api_url="https://instance.test/v1")
    http._state = ConnectionState(http=http, allowed_mentions=default)
    http.request = AsyncMock(return_value=message_payload())  # type: ignore[method-assign]
    return http


def sent_json(http: HTTPClient) -> dict[str, Any]:
    return http.request.call_args.kwargs["json"]  # type: ignore[attr-defined]


def test_payload_defaults_factories_and_repr() -> None:
    assert fluxer.AllowedMentions().to_dict() == {
        "parse": ["everyone", "users", "roles"],
        "replied_user": True,
    }
    assert fluxer.AllowedMentions.none().to_dict() == {
        "parse": [],
        "replied_user": False,
    }
    assert fluxer.AllowedMentions.all() == fluxer.AllowedMentions()
    assert repr(fluxer.AllowedMentions()) == (
        "AllowedMentions(everyone=True, users=True, roles=True, replied_user=True)"
    )


def test_targets_accept_objects_and_ids() -> None:
    user = fluxer.User(id=5, username="u")
    member = fluxer.GuildMember(user=fluxer.User(id=6, username="m"))
    role = SimpleNamespace(id=7)
    mentions = fluxer.AllowedMentions(
        users=[user, member, fluxer.Object(8), "9"], roles=[role]
    )
    # Fluxer rejects parse categories next to lists, so unset defaults turn off.
    assert mentions.to_dict() == {
        "parse": [],
        "users": ["5", "6", "8", "9"],
        "roles": ["7"],
        "replied_user": True,
    }
    assert fluxer.AllowedMentions(everyone=False, users=[], roles=True).to_dict() == {
        "parse": ["roles"],
        "replied_user": True,
    }


def test_explicit_category_next_to_a_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="everyone=True"):
        fluxer.AllowedMentions(everyone=True, users=[1]).to_dict()
    with pytest.raises(TypeError):
        fluxer.AllowedMentions(users=[True]).to_dict()


def test_merge_takes_only_explicit_fields() -> None:
    base = fluxer.AllowedMentions(everyone=False, replied_user=False)
    merged = base.merge(fluxer.AllowedMentions(users=[3]))
    assert merged.everyone is False and merged.replied_user is False
    assert merged.users == [3] and merged.roles
    assert merged.to_dict() == {"parse": [], "users": ["3"], "replied_user": False}


@pytest.mark.asyncio
async def test_send_uses_merges_and_overrides_the_client_default() -> None:
    http = http_client()
    await http.send_message(10, content="hi")
    assert "allowed_mentions" not in sent_json(http)

    http = http_client(fluxer.AllowedMentions(everyone=False))
    await http.send_message(10, content="hi")
    assert sent_json(http)["allowed_mentions"] == {
        "parse": ["users", "roles"],
        "replied_user": True,
    }
    await http.send_message(10, allowed_mentions=fluxer.AllowedMentions(roles=False))
    assert sent_json(http)["allowed_mentions"]["parse"] == ["users"]
    await http.send_message(10, allowed_mentions={"parse": []})
    assert sent_json(http)["allowed_mentions"] == {"parse": []}
    await http.send_message(10, mention_author=False)
    assert sent_json(http)["allowed_mentions"] == {
        "parse": ["users", "roles"],
        "replied_user": False,
    }


@pytest.mark.asyncio
async def test_mention_author_without_any_policy() -> None:
    http = http_client()
    await http.send_message(10, content="hi", mention_author=False)
    assert sent_json(http)["allowed_mentions"] == {
        "parse": ["everyone", "users", "roles"],
        "replied_user": False,
    }


@pytest.mark.asyncio
async def test_edits_apply_the_default_only_when_the_text_changes() -> None:
    http = http_client(fluxer.AllowedMentions.none())
    await http.edit_message(10, 100, flags=4)
    assert "allowed_mentions" not in sent_json(http)
    await http.edit_message(10, 100, content="new")
    assert sent_json(http)["allowed_mentions"] == {"parse": [], "replied_user": False}
    await http.edit_message(10, 100, allowed_mentions=None)
    assert sent_json(http)["allowed_mentions"] is None
    await http.edit_message(
        10, 100, content="new", allowed_mentions=fluxer.AllowedMentions(users=True)
    )
    assert sent_json(http)["allowed_mentions"]["parse"] == ["users"]
    await http.edit_message(
        10, 100, allowed_mentions=fluxer.AllowedMentions(users=True)
    )
    assert sent_json(http)["allowed_mentions"]["parse"] == [
        "everyone",
        "users",
        "roles",
    ]


@pytest.mark.asyncio
async def test_webhook_send_and_edit_use_the_default() -> None:
    http = http_client(fluxer.AllowedMentions.none())
    await http.execute_webhook(1, "token", content="hi")
    assert sent_json(http)["allowed_mentions"] == {"parse": [], "replied_user": False}
    await http.edit_webhook_message(1, "token", 2, content="new")
    assert sent_json(http)["allowed_mentions"] == {"parse": [], "replied_user": False}
    await http.edit_webhook_message(1, "token", 2, allowed_mentions=UNSET, flags=4)
    assert "allowed_mentions" not in sent_json(http)


@pytest.mark.asyncio
async def test_message_reply_and_channel_send_accept_mention_author() -> None:
    http = http_client()
    message = fluxer.Message.from_data(message_payload(), http)
    await message.reply("pong", mention_author=False)
    payload = sent_json(http)
    assert payload["message_reference"]["message_id"] == "100"
    assert payload["allowed_mentions"]["replied_user"] is False

    channel = fluxer.Channel(id=10, type=fluxer.ChannelType.GUILD_TEXT, _http=http)
    await channel.send("hi", allowed_mentions=fluxer.AllowedMentions(users=[5]))
    assert sent_json(http)["allowed_mentions"] == {
        "parse": [],
        "users": ["5"],
        "replied_user": True,
    }


def test_client_and_bot_option() -> None:
    policy = fluxer.AllowedMentions.none()
    client = fluxer.Client(allowed_mentions=policy)
    assert (
        client.allowed_mentions is policy and client._state.allowed_mentions is policy
    )
    client.allowed_mentions = None
    assert client._state.allowed_mentions is None
    with pytest.raises(TypeError):
        client.allowed_mentions = {"parse": []}  # type: ignore[assignment]
    bot = commands.Bot(command_prefix="!", allowed_mentions=policy)
    assert bot.allowed_mentions is policy
