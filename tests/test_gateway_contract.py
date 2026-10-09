"""Offline checks of command shapes and dispatch sequencing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from fluxer.http import HTTPClient

import pytest

from fluxer import Client, CustomActivity, Game, GatewayOpcode, Intents
from fluxer.gateway import Gateway, GatewayPayload


def gateway(dispatch=None):
    return Gateway(
        http_client=HTTPClient("test", api_url="https://instance.test/v1"),
        token="test",
        intents=Intents.default(),
        dispatch=dispatch or AsyncMock(),
    )


@pytest.mark.asyncio
async def test_presence_omission_clear_and_custom_status():
    gw = gateway()
    gw._send = AsyncMock()
    await gw.update_presence(status="idle")
    assert gw._send.call_args.args[0].d == {"status": "idle", "afk": False}
    await gw.update_presence(activity=None)
    assert gw._send.call_args.args[0].d["custom_status"] is None
    await gw.update_presence(activity=CustomActivity("Working"))
    assert gw._send.call_args.args[0].d["custom_status"] == {"text": "Working"}
    with pytest.raises(ValueError):
        await gw.update_presence(activity=Game("unsupported"))
    await gw._send_identify()
    assert "intents" not in gw._send.call_args.args[0].d


@pytest.mark.asyncio
async def test_dispatch_sequence_advances_after_processing_and_ack_stays_responsive():
    entered = asyncio.Event()
    release = asyncio.Event()
    processed = []

    async def dispatch(name, data):
        entered.set()
        await release.wait()
        processed.append(data)

    gw = gateway(dispatch)
    await gw._handle_payload_task(GatewayPayload(0, 1, 10, "FIRST"))
    await entered.wait()
    await gw._handle_payload_task(GatewayPayload(0, 2, 12, "SECOND"))
    assert gw._sequence is None
    gw._last_heartbeat_ack = False
    await gw._handle_payload_task(GatewayPayload(GatewayOpcode.HEARTBEAT_ACK))
    assert gw._last_heartbeat_ack
    release.set()
    await asyncio.wait_for(gw._dispatch_queue.join(), 1)
    assert processed == [1, 2]
    assert gw._sequence == 12
    await gw.close()


@pytest.mark.asyncio
async def test_callback_can_wait_for_next_event():
    client = Client()
    done = asyncio.Event()

    @client.on("first")
    async def first(data):
        assert await client.wait_for("second", timeout=1) == 2
        done.set()

    await client._dispatch("FIRST", 1)
    await client._dispatch("SECOND", 2)
    await asyncio.wait_for(done.wait(), 1)
    await client.close()


@pytest.mark.asyncio
async def test_invalid_sequence_discards_resume_state():
    gw = gateway()
    gw._session_id = "old"
    gw._sequence = 10
    gw._resume_gateway_url = "wss://old.test"
    await gw._handle_close_code(4007)
    assert (gw._session_id, gw._sequence, gw._resume_gateway_url) == (None, None, None)
    assert (
        gw._gateway_url("wss://node.test/prefix?existing=1")
        == "wss://node.test/prefix?existing=1&v=1&encoding=json"
    )


@pytest.mark.asyncio
async def test_close_awaits_owned_workers_and_discards_unsent_voice():
    gw = gateway()
    cancelled = []

    async def worker(name):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(name)

    gw._heartbeat_task = asyncio.create_task(worker("heartbeat"))
    gw._voice_state_task = asyncio.create_task(worker("voice"))
    await asyncio.sleep(0)
    await gw._voice_state_queue.put(
        GatewayPayload(GatewayOpcode.VOICE_STATE_UPDATE, {})
    )
    await gw.close()
    assert sorted(cancelled) == ["heartbeat", "voice"]
    await asyncio.wait_for(gw._voice_state_queue.join(), 1)


@pytest.mark.asyncio
async def test_latency_measures_heartbeat_round_trip(monkeypatch):
    clock = iter([100.0, 100.25])
    monkeypatch.setattr("fluxer.gateway.time.perf_counter", lambda: next(clock))
    gw = gateway()
    gw._send = AsyncMock()
    assert gw.latency == float("inf")
    # An ACK with no heartbeat in flight must not produce a measurement.
    await gw._handle_payload(GatewayPayload(GatewayOpcode.HEARTBEAT_ACK))
    assert gw.latency == float("inf")
    await gw._send_heartbeat()
    await gw._handle_payload(GatewayPayload(GatewayOpcode.HEARTBEAT_ACK))
    assert gw.latency == pytest.approx(0.25)
    await gw.close()


def test_client_latency_is_nan_without_gateway():
    client = Client()
    assert client.latency != client.latency


@pytest.mark.asyncio
async def test_first_heartbeat_is_sent_immediately():
    gw = gateway()
    gw._ws = MagicMock(closed=False)
    gw._send = AsyncMock()
    gw._heartbeat_interval = 3600
    await gw._start_heartbeat()
    await asyncio.sleep(0)
    gw._send.assert_awaited_once()
    assert gw._send.call_args.args[0].op == GatewayOpcode.HEARTBEAT
    await gw._stop_heartbeat()
