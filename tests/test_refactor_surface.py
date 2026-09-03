from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

import fluxer
import fluxer.channel
import fluxer.message
import fluxer.webhook
from fluxer.gateway import Gateway, GatewayPayload


class FakeHTTP:
    def __init__(self) -> None:
        self.sent: list[tuple[int | str, dict[str, Any]]] = []
        self.edited: list[tuple[int | str, int | str, dict[str, Any]]] = []
        self.deleted: list[tuple[int | str, int | str]] = []
        self.pinned: list[tuple[int | str, int | str]] = []
        self.unpinned: list[tuple[int | str, int | str]] = []
        self.acked: list[tuple[int | str, int | str]] = []
        self.webhook_edited: list[tuple[int | str, str, int | str, dict[str, Any]]] = []
        self.webhook_deleted: list[tuple[int | str, str, int | str]] = []

    async def send_message(
        self, channel_id: int | str, **kwargs: Any
    ) -> dict[str, Any]:
        self.sent.append((channel_id, kwargs))
        return self._message(channel_id, "100", kwargs.get("content", ""))

    async def get_message(
        self, channel_id: int | str, message_id: int | str
    ) -> dict[str, Any]:
        return self._message(channel_id, message_id, "fetched")

    async def edit_message(
        self, channel_id: int | str, message_id: int | str, **kwargs: Any
    ) -> dict[str, Any]:
        self.edited.append((channel_id, message_id, kwargs))
        return self._message(channel_id, message_id, kwargs.get("content", ""))

    async def delete_message(
        self, channel_id: int | str, message_id: int | str
    ) -> None:
        self.deleted.append((channel_id, message_id))

    async def pin_message(self, channel_id: int | str, message_id: int | str) -> None:
        self.pinned.append((channel_id, message_id))

    async def unpin_message(self, channel_id: int | str, message_id: int | str) -> None:
        self.unpinned.append((channel_id, message_id))

    async def ack_message(self, channel_id: int | str, message_id: int | str) -> None:
        self.acked.append((channel_id, message_id))

    async def edit_webhook_message(
        self, webhook_id: int | str, token: str, message_id: int | str, **kwargs: Any
    ) -> dict[str, Any]:
        self.webhook_edited.append((webhook_id, token, message_id, kwargs))
        return self._message(10, message_id, kwargs.get("content", ""))

    async def delete_webhook_message(
        self, webhook_id: int | str, token: str, message_id: int | str
    ) -> None:
        self.webhook_deleted.append((webhook_id, token, message_id))

    def _message(
        self, channel_id: int | str, message_id: int | str, content: str
    ) -> dict[str, Any]:
        return {
            "id": str(message_id),
            "channel_id": str(channel_id),
            "content": content,
            "author": {"id": "42", "username": "tester"},
            "timestamp": "2026-01-01T00:00:00+00:00",
        }


def test_public_surface_imports() -> None:
    assert fluxer.message.PartialMessage is fluxer.PartialMessage
    assert fluxer.message.MessageReference is fluxer.MessageReference
    assert fluxer.webhook.WebhookMessage is fluxer.WebhookMessage
    assert fluxer.Colour is fluxer.Color
    assert not hasattr(fluxer.channel, "StageChannel")
    assert not hasattr(fluxer.channel, "StoreChannel")


@pytest.mark.asyncio
async def test_message_reference_partial_and_allowed_mentions() -> None:
    http = FakeHTTP()
    channel = fluxer.Channel(
        id=10, type=fluxer.ChannelType.GUILD_TEXT, _http=cast(Any, http)
    )
    mentions = fluxer.AllowedMentions.none()
    reference = fluxer.MessageReference(message_id=99, channel_id=10)

    message = await channel.send(
        "hello",
        allowed_mentions=mentions,
        message_reference=reference.to_dict(),
    )

    assert message.jump_url.endswith("/@me/10/100")
    assert http.sent[0][1]["allowed_mentions"] is mentions
    assert http.sent[0][1]["message_reference"] == {
        "message_id": "99",
        "channel_id": "10",
    }

    partial = channel.get_partial_message(100)
    assert partial.jump_url.endswith("/@me/10/100")
    assert (await partial.fetch()).content == "fetched"
    assert (await partial.edit(content="edited")).content == "edited"
    await partial.edit(embed=fluxer.Embed(title="Partial edit"))
    await partial.pin()
    await partial.unpin()
    await partial.ack()
    await partial.delete()

    assert http.pinned == [(10, 100)]
    assert http.unpinned == [(10, 100)]
    assert http.acked == [(10, 100)]
    assert http.deleted == [(10, 100)]
    assert http.edited[1][2]["embeds"] == [{"title": "Partial edit"}]


@pytest.mark.asyncio
async def test_message_edit_accepts_single_embed() -> None:
    http = FakeHTTP()
    message = fluxer.Message.from_data(http._message(10, 100, "hello"), cast(Any, http))

    await message.edit(embed=fluxer.Embed(title="Menu page"))

    assert http.edited == [
        (10, 100, {"content": None, "embeds": [{"title": "Menu page"}]})
    ]


@pytest.mark.asyncio
async def test_webhook_message_helpers() -> None:
    http = FakeHTTP()
    webhook = fluxer.Webhook.from_url(
        "https://api.fluxer.app/v1/webhooks/123/token-value",
        http=cast(Any, http),
    )
    message = fluxer.WebhookMessage.from_data(
        http._message(10, 700, "hello"),
        cast(Any, http),
        webhook_id=webhook.id,
        token=webhook.token,
    )

    edited = await webhook.edit_message(700, content="edited")
    await message.delete()

    assert edited.content == "edited"
    assert http.webhook_edited == [(123, "token-value", 700, {"content": "edited"})]
    assert http.webhook_deleted == [(123, "token-value", 700)]


@pytest.mark.asyncio
async def test_gateway_helper_payloads() -> None:
    sent: list[GatewayPayload] = []
    gateway = Gateway(
        http_client=None,
        token="token",
        intents=fluxer.Intents.default(),
        dispatch=cast(Any, lambda event, data: None),
    )

    async def fake_send(payload: GatewayPayload) -> None:
        sent.append(payload)

    gateway._send = fake_send

    await gateway.update_presence(activity=fluxer.Game("tests"), afk=True, since=1.0)
    await gateway.request_guild_members(guild_id=20, query="a", limit=1, nonce="n")
    await gateway.request_lazy_members(guild_id=20, ranges=[[0, 99]])
    await gateway.request_guild_counts([20])
    await gateway.request_channel_member_counts([10])
    await gateway.update_voice_state(guild_id="20", channel_id="10")
    await asyncio.wait_for(gateway._voice_state_queue.join(), timeout=1.0)
    await gateway.close()

    assert sent[0].op == fluxer.GatewayOpcode.PRESENCE_UPDATE
    assert sent[1].op == fluxer.GatewayOpcode.REQUEST_GUILD_MEMBERS
    assert sent[2].op == fluxer.GatewayOpcode.LAZY_REQUEST
    assert sent[3].op == fluxer.GatewayOpcode.REQUEST_GUILD_COUNTS
    assert sent[4].op == fluxer.GatewayOpcode.REQUEST_CHANNEL_MEMBER_COUNTS
    assert sent[5].op == fluxer.GatewayOpcode.VOICE_STATE_UPDATE


def test_voice_state_connection_id_parsing() -> None:
    state = fluxer.VoiceState.from_data(
        {
            "user_id": "42",
            "guild_id": "20",
            "channel_id": "10",
            "connection_id": "conn-a",
        }
    )

    assert state.connection_id == "conn-a"


@pytest.mark.asyncio
async def test_client_voice_state_cache_seed_update_remove_and_count() -> None:
    client = fluxer.Client()
    guild_payload = {
        "id": "20",
        "name": "Guild",
        "voice_states": [
            {
                "user_id": "42",
                "channel_id": "10",
                "connection_id": "conn-a",
            },
            {
                "user_id": "42",
                "channel_id": "10",
                "connection_id": "conn-b",
            },
            {
                "user_id": "43",
                "channel_id": "10",
                "connection_id": "conn-c",
            },
        ],
    }

    await client._dispatch("GUILD_CREATE", guild_payload)

    assert len(client.get_guild_voice_states(20)) == 3
    assert len(client.get_channel_voice_states(10)) == 3
    assert client.get_channel_voice_user_count(10) == 2
    assert client.get_voice_state(20, 42) is not None

    await client._dispatch(
        "VOICE_STATE_UPDATE",
        {
            "user_id": "42",
            "guild_id": "20",
            "channel_id": "11",
            "connection_id": "conn-a",
        },
    )

    assert len(client.get_channel_voice_states(10)) == 2
    assert len(client.get_channel_voice_states(11)) == 1

    await client._dispatch(
        "VOICE_STATE_UPDATE",
        {
            "user_id": "42",
            "guild_id": "20",
            "channel_id": None,
            "connection_id": "conn-b",
        },
    )

    assert len(client.get_guild_voice_states(20)) == 2
    assert len(client.get_channel_voice_states(10)) == 1
    assert client.get_channel_voice_user_count(10) == 1


@pytest.mark.asyncio
async def test_client_wait_for_resolves_matching_events() -> None:
    client = fluxer.Client()
    payload = object()
    waiter = asyncio.create_task(
        client.wait_for("raw_reaction_add", check=lambda event: event is payload)
    )

    await asyncio.sleep(0)
    await client._fire("on_raw_reaction_add", payload)

    assert await asyncio.wait_for(waiter, timeout=1.0) is payload


@pytest.mark.asyncio
async def test_client_wait_for_ignores_non_matching_events() -> None:
    client = fluxer.Client()
    payload = object()
    waiter = asyncio.create_task(
        client.wait_for(
            "raw_reaction_add", check=lambda event: event is payload, timeout=0.01
        )
    )

    await asyncio.sleep(0)
    await client._fire("on_raw_reaction_add", object())

    with pytest.raises(asyncio.TimeoutError):
        await waiter
