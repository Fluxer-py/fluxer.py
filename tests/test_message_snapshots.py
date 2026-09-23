"""Typed forwarded-message snapshots."""

from datetime import datetime, timezone
from typing import Any, cast

import pytest

import fluxer
from fluxer import message as message_facade
from fluxer.models import MessageSnapshot as ModelMessageSnapshot


def message_payload(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "10",
        "channel_id": "20",
        "author": {"id": "30", "username": "author"},
        "timestamp": "2026-01-01T00:00:00Z",
        "message_snapshots": snapshots,
    }


@pytest.mark.parametrize("model", [fluxer.Message, fluxer.WebhookMessage])
def test_flat_snapshots_parse_on_both_message_models(model: Any) -> None:
    first = {
        "timestamp": "2026-01-02T03:04:05Z",
        "edited_timestamp": "2026-01-03T04:05:06+00:00",
        "content": "forwarded text",
        "type": 1,
        "flags": (1 << 2) | (1 << 60),
        "mentions": ["41", "42"],
        "mention_roles": ["51"],
        "mention_channels": [{"id": "61", "name": "general"}],
        "embeds": [{"title": "example"}],
        "attachments": [
            {
                "id": "71", "filename": "file.txt", "size": 4,
                "url": "https://media.example.test/file.txt",
            }
        ],
        "stickers": [{"id": "81", "name": "wave"}],
        "future_field": {"kept": True},
    }
    second = {"timestamp": "2026-01-04T00:00:00Z"}

    message = model.from_data(message_payload([first, second]))
    assert len(message.message_snapshots) == 2
    snapshot, minimal = message.message_snapshots
    assert isinstance(snapshot, fluxer.MessageSnapshot)
    assert snapshot.timestamp == first["timestamp"]
    assert snapshot.created_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert snapshot.edited_timestamp == first["edited_timestamp"]
    assert snapshot.edited_at == datetime(2026, 1, 3, 4, 5, 6, tzinfo=timezone.utc)
    assert snapshot.content == "forwarded text"
    assert snapshot.type == 1
    assert isinstance(snapshot.flags, fluxer.MessageFlags)
    assert snapshot.flags.suppress_embeds
    assert int(snapshot.flags) == first["flags"]
    assert snapshot.mentions == [41, 42]
    assert snapshot.mention_roles == [51]
    assert snapshot.mention_channels == first["mention_channels"]
    assert snapshot.embeds == first["embeds"]
    assert isinstance(snapshot.attachments[0], message_facade.Attachment)
    assert snapshot.attachments[0].id == 71
    assert isinstance(snapshot.stickers[0], fluxer.Sticker)
    assert snapshot.stickers[0].id == 81
    assert snapshot.raw_data["future_field"] == {"kept": True}

    assert isinstance(minimal, fluxer.MessageSnapshot)
    assert minimal.content == ""
    assert minimal.edited_timestamp is None
    assert minimal.edited_at is None
    assert minimal.type == 0
    assert int(minimal.flags) == 0
    assert minimal.mentions == minimal.mention_roles == []
    assert minimal.mention_channels == minimal.embeds == []
    assert minimal.attachments == minimal.stickers == []
    assert minimal.raw_data == second


@pytest.mark.parametrize("model", [fluxer.Message, fluxer.WebhookMessage])
def test_empty_snapshot_array_stays_empty(model: Any) -> None:
    assert model.from_data(message_payload([])).message_snapshots == []


def test_snapshot_export_and_required_timestamp() -> None:
    assert fluxer.MessageSnapshot is ModelMessageSnapshot
    assert fluxer.MessageSnapshot is message_facade.MessageSnapshot
    with pytest.raises(KeyError, match="timestamp"):
        fluxer.MessageSnapshot.from_data({})

    direct = fluxer.MessageSnapshot(
        timestamp="2026-01-02T00:00:00Z", flags=cast(Any, 1 << 13)
    )
    assert isinstance(direct.flags, fluxer.MessageFlags)
    assert direct.flags.voice_message
