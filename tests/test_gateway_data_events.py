"""Gateway payload callbacks and modeled reaction-add events."""

import asyncio
from typing import Any

import pytest

import fluxer


def reaction_payload(user_id: int = 42, *, message_id: int = 10) -> dict[str, Any]:
    """Build a minimal Gateway reaction payload."""
    return {
        "message_id": str(message_id),
        "channel_id": "20",
        "user_id": str(user_id),
        "emoji": {"name": "ok"},
    }


@pytest.mark.parametrize("source", ["member", "cache", "id_only"])
@pytest.mark.asyncio
async def test_reaction_add_uses_cached_message_and_resolves_user(source: str) -> None:
    client = fluxer.Client()
    message = fluxer.Message(
        id=10,
        channel_id=20,
        content="hello",
        author=fluxer.User(id=1),
        timestamp="2026-01-01T00:00:00+00:00",
    )
    client._state.store_message(message)
    data = reaction_payload()
    if source == "member":
        data["member"] = {"user": {"id": "42", "username": "from_member"}}
    elif source == "cache":
        cached_user = fluxer.User(id=42, username="from_cache")
        client._users[42] = cached_user

    modeled: list[tuple[Any, Any]] = []
    raw: list[Any] = []
    payloads: list[Any] = []

    @client.event
    async def on_reaction_add(reaction: Any, user: fluxer.User) -> None:
        modeled.append((reaction, user))

    @client.event
    async def on_raw_reaction_add(event: Any) -> None:
        raw.append(event)

    @client.event
    async def on_message_reaction_add_data(payload: dict[str, Any]) -> None:
        payloads.append(payload)

    await client._dispatch("MESSAGE_REACTION_ADD", data)

    assert len(modeled) == len(raw) == len(payloads) == 1
    reaction, user = modeled[0]
    assert reaction is message.reactions[0]
    assert reaction.count == 1
    assert reaction.message is message
    assert user.id == 42
    assert (
        user.username
        == {
            "member": "from_member",
            "cache": "from_cache",
            "id_only": "",
        }[source]
    )
    assert raw[0].message_id == 10
    assert payloads[0] is data
    assert data["user_id"] == "42"
    await client.close()


@pytest.mark.asyncio
async def test_uncached_reaction_still_emits_raw_and_data_events() -> None:
    client = fluxer.Client()
    data = reaction_payload(message_id=999)
    modeled: list[Any] = []
    raw: list[Any] = []
    payloads: list[Any] = []

    @client.event
    async def on_reaction_add(reaction: Any, user: fluxer.User) -> None:
        modeled.append((reaction, user))

    @client.event
    async def on_raw_reaction_add(event: Any) -> None:
        raw.append(event)

    @client.event
    async def on_message_reaction_add_data(payload: dict[str, Any]) -> None:
        payloads.append(payload)

    await client._dispatch("MESSAGE_REACTION_ADD", data)
    assert modeled == []
    assert len(raw) == 1 and raw[0].message_id == 999
    assert payloads == [data] and payloads[0] is data
    await client.close()


@pytest.mark.asyncio
async def test_data_callbacks_cover_modeled_unhandled_and_early_return_events() -> None:
    client = fluxer.Client()
    message_data = {
        "id": "10",
        "channel_id": "20",
        "content": "hello",
        "author": {"id": "42", "username": "writer"},
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    seen: list[tuple[str, Any]] = []

    @client.event
    async def on_message(message: fluxer.Message) -> None:
        seen.append(("modeled", message))

    @client.event
    async def on_message_create_data(data: dict[str, Any]) -> None:
        seen.append(("message_data", data))

    @client.event
    async def on_voice_server_update_data(data: dict[str, Any]) -> None:
        seen.append(("voice_data", data))

    @client.event
    async def on_custom_event_data(data: dict[str, Any]) -> None:
        seen.append(("custom_data", data))

    @client.event
    async def on_custom_event(data: dict[str, Any]) -> None:
        seen.append(("custom", data))

    waiter = asyncio.create_task(client.wait_for("message_create_data"))
    await asyncio.sleep(0)
    await client._dispatch("MESSAGE_CREATE", message_data)
    assert await waiter is message_data
    assert ("message_data", message_data) in seen
    assert any(
        name == "modeled" and isinstance(item, fluxer.Message) for name, item in seen
    )

    voice_data = {"guild_id": None, "endpoint": "ignored"}
    await client._dispatch("VOICE_SERVER_UPDATE", voice_data)
    assert ("voice_data", voice_data) in seen

    custom_data = {"key": "value"}
    await client._dispatch("CUSTOM_EVENT", custom_data)
    assert ("custom_data", custom_data) in seen
    assert ("custom", custom_data) in seen
    assert next(item for name, item in seen if name == "custom_data") is custom_data
    await client.close()


@pytest.mark.asyncio
async def test_data_callback_does_not_wrap_non_dictionary_payload() -> None:
    client = fluxer.Client()
    payload = ["original", {"nested": True}]
    seen: list[Any] = []

    @client.event
    async def on_custom_event_data(data: Any) -> None:
        seen.append(data)

    await client._dispatch("CUSTOM_EVENT", payload)
    assert seen == [payload]
    assert seen[0] is payload
    await client.close()
