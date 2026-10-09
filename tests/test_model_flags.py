"""Fluxer message and attachment flag access."""

from typing import Any, cast

import pytest

import fluxer
from fluxer.models.attachment import Attachment


def message_payload(**extra: Any) -> dict[str, Any]:
    """Build a minimal message payload."""
    return {
        "id": "10",
        "channel_id": "20",
        "author": {"id": "30", "username": "author"},
        "timestamp": "2026-01-01T00:00:00+00:00",
        **extra,
    }


@pytest.mark.parametrize(
    ("bit", "attribute"),
    [
        (1 << 2, "suppress_embeds"),
        (1 << 12, "suppress_notifications"),
        (1 << 13, "voice_message"),
    ],
)
def test_message_flag_bits(bit: int, attribute: str) -> None:
    flags = fluxer.MessageFlags(bit)
    assert getattr(flags, attribute) is True
    assert (
        sum((flags.suppress_embeds, flags.suppress_notifications, flags.voice_message))
        == 1
    )
    assert int(flags) == flags.value == bit


@pytest.mark.parametrize(
    ("bit", "attribute"),
    [
        (1 << 3, "is_spoiler"),
        (1 << 4, "contains_explicit_media"),
        (1 << 5, "is_animated"),
    ],
)
def test_attachment_flag_bits(bit: int, attribute: str) -> None:
    flags = fluxer.AttachmentFlags(bit)
    assert getattr(flags, attribute) is True
    assert (
        sum((flags.is_spoiler, flags.contains_explicit_media, flags.is_animated)) == 1
    )
    assert int(flags) == flags.value == bit


def test_combined_zero_and_unknown_bits_are_preserved() -> None:
    unknown = 1 << 60
    message_flags = fluxer.MessageFlags((1 << 2) | (1 << 13) | unknown)
    assert message_flags.suppress_embeds
    assert not message_flags.suppress_notifications
    assert message_flags.voice_message
    assert int(message_flags) == (1 << 2) | (1 << 13) | unknown

    attachment_flags = fluxer.AttachmentFlags((1 << 3) | (1 << 5) | unknown)
    assert attachment_flags.is_spoiler
    assert not attachment_flags.contains_explicit_media
    assert attachment_flags.is_animated
    assert int(attachment_flags) == (1 << 3) | (1 << 5) | unknown

    assert not fluxer.MessageFlags().suppress_embeds
    assert not fluxer.MessageFlags().suppress_notifications
    assert not fluxer.MessageFlags().voice_message
    assert not fluxer.AttachmentFlags().is_spoiler
    assert not fluxer.AttachmentFlags().contains_explicit_media
    assert not fluxer.AttachmentFlags().is_animated


@pytest.mark.parametrize("model", [fluxer.Message, fluxer.WebhookMessage])
def test_message_models_parse_and_accept_integer_masks(model: Any) -> None:
    parsed = model.from_data(message_payload(flags=(1 << 2) | (1 << 12)))
    assert isinstance(parsed.flags, fluxer.MessageFlags)
    assert parsed.flags.suppress_embeds
    assert parsed.flags.suppress_notifications
    assert not parsed.flags.voice_message

    direct = model(
        id=10,
        channel_id=20,
        content="hello",
        author=fluxer.User(id=30),
        timestamp="2026-01-01T00:00:00+00:00",
        flags=cast(Any, 1 << 13),
    )
    assert isinstance(direct.flags, fluxer.MessageFlags)
    assert direct.flags.voice_message
    assert int(direct.flags) == 1 << 13


def test_attachment_spoiler_uses_flag_and_serializes_integer_mask() -> None:
    attachment = Attachment.from_data(
        {
            "id": "50",
            "filename": "ordinary.txt",
            "size": 3,
            "url": "https://media.example.test/file",
            "flags": (1 << 3) | (1 << 4),
        }
    )
    assert isinstance(attachment.flags, fluxer.AttachmentFlags)
    assert attachment.is_spoiler()
    assert attachment.flags.contains_explicit_media
    assert not attachment.flags.is_animated
    assert attachment.to_dict()["flags"] == (1 << 3) | (1 << 4)
    assert isinstance(attachment.to_dict()["flags"], int)

    direct = Attachment(
        id=51,
        filename="SPOILER_file.txt",
        size=3,
        url="https://media.example.test/file",
        flags=cast(Any, 0),
    )
    assert isinstance(direct.flags, fluxer.AttachmentFlags)
    assert not direct.is_spoiler()
    assert direct.to_dict()["flags"] == 0

    other = Attachment(id=52, filename="other.txt", size=3, url=None)
    assert direct.flags is not other.flags
