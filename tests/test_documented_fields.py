"""Fields from the Fluxer object structures that models expose as attributes."""

from typing import Any, TypeVar

import pytest

import fluxer
from fluxer.fluxer_models import MFAState, WebAuthnCredential
from fluxer.models import Role
from fluxer.models.message import Message
from fluxer.models.reaction import RawReactionActionEvent

T = TypeVar("T")


def _required(value: T | None) -> T:
    assert value is not None
    return value


def message_payload(**extra: Any) -> dict[str, Any]:
    return {
        "id": "10",
        "channel_id": "2",
        "author": {"id": "3", "username": "author"},
        "content": "hello",
        "timestamp": "2026-01-01T00:00:00Z",
        **extra,
    }


def test_role_unicode_emoji() -> None:
    assert Role.from_data({"id": "1", "unicode_emoji": "🔥"}).unicode_emoji == "🔥"
    assert Role.from_data({"id": "1"}).unicode_emoji is None


def test_sticker_nsfw() -> None:
    assert fluxer.Sticker.from_data({"id": "1", "name": "s", "nsfw": True}).nsfw
    assert not fluxer.Sticker.from_data({"id": "1", "name": "s"}).nsfw


def test_message_create_additions() -> None:
    message = Message.from_data(
        message_payload(channel_type=3, nicks={"3": "nick"}, mention_here=True)
    )
    assert message.channel_type == 3
    assert message.nicks == {3: "nick"}
    assert message.mention_here is True
    plain = Message.from_data(message_payload())
    assert plain.channel_type is None and plain.nicks == {} and not plain.mention_here


def test_webauthn_rp_id_and_mfa_backup_codes() -> None:
    credential = WebAuthnCredential.from_data({"id": "c", "rp_id": "fluxer.app"})
    assert credential.rp_id == "fluxer.app"
    state = MFAState.from_data(
        {"totp": True, "webauthn": False, "backup_codes": True, "has_mfa": True}
    )
    assert state.backup_codes is True


def test_raw_reaction_member() -> None:
    base = {
        "user_id": "3",
        "channel_id": "2",
        "message_id": "10",
        "emoji": {"name": "x"},
    }
    raw = RawReactionActionEvent.from_data(
        {**base, "guild_id": "1", "member": {"user": {"id": "3"}, "nick": "n"}},
        "REACTION_ADD",
    )
    member = _required(raw.member)
    assert member.nick == "n" and member.guild_id == 1
    assert RawReactionActionEvent.from_data(base, "REACTION_ADD").member is None


@pytest.mark.asyncio
async def test_guild_ready_fields_and_voice_states() -> None:
    client = fluxer.Client()
    await client._dispatch(
        "GUILD_CREATE",
        {
            "id": "1",
            "properties": {"name": "guild", "owner_id": "9"},
            "joined_at": "2026-01-01T00:00:00Z",
            "channels": [{"id": "2", "type": 2, "name": "voice"}],
            "voice_states": [
                {
                    "guild_id": "1",
                    "channel_id": "2",
                    "user_id": "3",
                    "session_id": "s",
                    "member": {"user": {"id": "3"}},
                }
            ],
        },
    )
    guild = _required(client.get_guild(1))
    assert guild.joined_at == "2026-01-01T00:00:00Z"
    assert [state.user_id for state in guild.voice_states] == [3]

    await client._dispatch(
        "GUILD_DELETE", {"id": "1", "unavailable": True, "unavailable_hidden": True}
    )
    assert guild.unavailable and guild.unavailable_hidden
    await client._dispatch("GUILD_CREATE", {"id": "1", "properties": {"name": "g"}})
    assert not guild.unavailable and not guild.unavailable_hidden
    await client.close()


@pytest.mark.asyncio
async def test_gateway_raw_reaction_member_is_cached_member() -> None:
    client = fluxer.Client()
    await client._dispatch(
        "GUILD_CREATE",
        {
            "id": "1",
            "properties": {"name": "guild"},
            "channels": [{"id": "2", "type": 0}],
            "members": [{"user": {"id": "3", "username": "a"}}],
        },
    )
    events: list[RawReactionActionEvent] = []

    @client.event
    async def on_raw_reaction_add(event: RawReactionActionEvent) -> None:
        events.append(event)

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
    assert events[0].member is client.get_member(1, 3)
    await client.close()
