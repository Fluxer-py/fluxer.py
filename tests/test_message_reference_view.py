"""Nested reference access for messages and webhook messages."""

from typing import Any

import pytest

from fluxer import DeletedReferencedMessage, Message, MessageReference, WebhookMessage


def payload(**extra: Any) -> dict[str, Any]:
    """Build a minimal Fluxer message payload."""
    return {
        "id": "10",
        "channel_id": "20",
        "author": {"id": "30", "username": "author"},
        "timestamp": "2026-01-01T00:00:00+00:00",
        **extra,
    }


@pytest.mark.parametrize("model", [Message, WebhookMessage])
def test_resolved_reference_is_same_metadata_object(model: Any) -> None:
    referenced = payload(id="9", content="original")
    message = model.from_data(
        payload(
            message_reference={"message_id": "9", "channel_id": "20"},
            referenced_message=referenced,
        )
    )

    assert message.reference is message.message_reference
    assert isinstance(message.reference, MessageReference)
    assert message.reference.resolved is message.referenced_message
    assert isinstance(message.reference.resolved, Message)
    assert message.reference.resolved.content == "original"
    assert message.reference.to_dict() == {
        "message_id": "9", "channel_id": "20"
    }

    replacement = Message.from_data(payload(id="8", content="replacement"))
    message.referenced_message = replacement
    assert message.reference.resolved is replacement
    assert message.message_reference.resolved is replacement
    assert message.reference.to_dict() == {
        "message_id": "9", "channel_id": "20"
    }


@pytest.mark.parametrize("model", [Message, WebhookMessage])
def test_deleted_and_unresolved_references(model: Any) -> None:
    deleted = model.from_data(
        payload(message_reference={"message_id": "9"}, referenced_message=None)
    )
    assert deleted.reference is deleted.message_reference
    assert isinstance(deleted.reference.resolved, DeletedReferencedMessage)
    assert deleted.reference.resolved.id == 9

    unresolved = model.from_data(payload(message_reference={"message_id": "9"}))
    assert unresolved.reference is unresolved.message_reference
    assert unresolved.reference.resolved is None
    assert unresolved.reference.to_dict() == {"message_id": "9"}


@pytest.mark.parametrize("model", [Message, WebhookMessage])
def test_reference_absence_and_read_only_resolution(model: Any) -> None:
    message = model.from_data(payload())
    assert message.reference is None

    no_metadata = model.from_data(payload(referenced_message=payload(id="9")))
    assert no_metadata.reference is None
    assert isinstance(no_metadata.referenced_message, Message)

    reference = MessageReference(message_id=9)
    assert reference.resolved is None
    with pytest.raises(AttributeError):
        reference.resolved = message  # type: ignore[misc]
    assert reference.to_dict() == {"message_id": "9"}
