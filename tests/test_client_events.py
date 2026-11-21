"""Client lifecycle events: on_error, on_connect, on_disconnect and debug events."""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import fluxer
from fluxer import gateway as gateway_module
from fluxer.gateway import Gateway, GatewayPayload
from fluxer.http import HTTPClient


@pytest.mark.asyncio
async def test_on_error_receives_event_name_and_arguments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = fluxer.Client()
    seen: list[tuple[Any, ...]] = []
    done = asyncio.Event()

    @client.event
    async def on_message(message: Any) -> None:
        raise RuntimeError("boom")

    @client.event
    async def on_error(event: str, *args: Any) -> None:
        import sys

        seen.append((event, args, type(sys.exc_info()[1])))
        done.set()

    client.dispatch("on_message", "payload")
    await asyncio.wait_for(done.wait(), 1)
    assert seen == [("on_message", ("payload",), RuntimeError)]

    client.remove_listener(on_error)
    with caplog.at_level(logging.ERROR, logger="fluxer.client"):
        await client._run_event_handler("on_message", on_message, "payload")
    assert "Error in event handler 'on_message'" in caplog.text
    await client.close()


@pytest.mark.asyncio
async def test_manual_dispatch_resolves_wait_for() -> None:
    client = fluxer.Client()
    waiter = asyncio.create_task(client.wait_for("command", timeout=1))
    await asyncio.sleep(0)
    client.dispatch("on_command", "ctx")
    assert await waiter == "ctx"
    await client.close()


@pytest.mark.asyncio
async def test_gateway_connect_disconnect_and_debug_events() -> None:
    notified: list[tuple[Any, ...]] = []

    class FakeSocket:
        closed = False
        close_code = None

        def __init__(self) -> None:
            self.messages = [
                SimpleNamespace(
                    type=gateway_module.aiohttp.WSMsgType.TEXT, data='{"op": 11}'
                )
            ]
            self.send_str = AsyncMock()

        def __aiter__(self) -> "FakeSocket":
            return self

        async def __anext__(self) -> Any:
            if not self.messages:
                raise StopAsyncIteration
            return self.messages.pop(0)

        async def close(self, **_: Any) -> None:
            self.closed = True

    socket = FakeSocket()
    gw = Gateway(
        http_client=HTTPClient("test", api_url="https://instance.test/v1"),
        token="test",
        intents=fluxer.Intents.default(),
        dispatch=AsyncMock(),
        notify=lambda *args: notified.append(args),
        debug_events=True,
    )
    gw._session = MagicMock(ws_connect=AsyncMock(return_value=socket))
    await gw._connect_and_run("wss://gateway.test")
    assert notified[0] == ("on_connect",)
    assert ("on_socket_raw_receive", '{"op": 11}') in notified
    assert notified[-1] == ("on_disconnect",)

    gw._ws = socket  # type: ignore[assignment]
    socket.closed = False
    await gw._send(GatewayPayload(1, None))
    assert notified[-1][0] == "on_socket_raw_send"
    await gw._handle_payload(GatewayPayload(0, {}, 5, "MESSAGE_ACK"))
    assert ("on_socket_event_type", "MESSAGE_ACK") in notified

    quiet: list[tuple[Any, ...]] = []
    gw._notify, gw._debug_events = (lambda *args: quiet.append(args)), False
    await gw._handle_payload(GatewayPayload(0, {}, 6, "MESSAGE_ACK"))
    assert quiet == []
    await gw.close()
