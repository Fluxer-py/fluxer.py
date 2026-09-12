"""Exercise voice identity and cleanup without installing or contacting LiveKit."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from fluxer import Client, VoiceState


@pytest.fixture
def voice_module(monkeypatch):
    rtc = types.ModuleType("livekit.rtc")

    class Room:
        def __init__(self):
            self.handlers = {}
            self.grant = None
            self.closed = False

        def on(self, name, callback):
            self.handlers[name] = callback

        async def connect(self, endpoint, token):
            self.grant = (endpoint, token)

        async def disconnect(self):
            self.closed = True
            if "disconnected" in self.handlers:
                self.handlers["disconnected"]()

    setattr(rtc, "Room", Room)
    livekit = types.ModuleType("livekit")
    setattr(livekit, "rtc", rtc)
    monkeypatch.setitem(sys.modules, "livekit", livekit)
    monkeypatch.setitem(sys.modules, "livekit.rtc", rtc)
    path = Path(__file__).parents[1] / "fluxer" / "voice.py"
    spec = importlib.util.spec_from_file_location("fluxer._voice_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_grant_identity_and_disconnect(voice_module):
    gateway = types.SimpleNamespace(is_connected=True, update_voice_state=AsyncMock())
    vc = voice_module.VoiceClient(1, 2, gateway)
    await vc._on_voice_server_update(
        "wss://issued.test/room", "issued-token", "connection-a"
    )
    await vc._wait_until_connected()
    assert vc.is_connected
    room = vc._room
    assert room.grant == ("wss://issued.test/room", "issued-token")
    await vc.disconnect()
    assert not vc.is_connected and room.closed
    assert (
        gateway.update_voice_state.call_args.kwargs["connection_id"] == "connection-a"
    )
    await vc.disconnect()
    assert gateway.update_voice_state.await_count == 1


@pytest.mark.asyncio
async def test_remote_disconnect_changes_local_state(voice_module):
    vc = voice_module.VoiceClient(1, 2, types.SimpleNamespace())
    await vc._on_voice_server_update("wss://issued.test", "token", "connection-a")
    vc._room.handlers["disconnected"]()
    assert not vc.is_connected


def test_nullable_voice_user_and_stale_version():
    assert VoiceState.from_data({"user_id": None}).user_id is None
    client = Client()
    payload = {
        "guild_id": "1",
        "user_id": "3",
        "channel_id": "2",
        "connection_id": "a",
        "version": 10,
    }
    current = client._store_voice_state(payload)
    assert (
        client._store_voice_state({**payload, "channel_id": None, "version": 9})
        is current
    )
    assert client.get_voice_state(1, 3) is current
    client._store_voice_state({**payload, "channel_id": None, "version": 11})
    assert client.get_voice_state(1, 3) is None

    client._store_voice_state(payload)
    assert client.get_voice_state(1, 3) is None
