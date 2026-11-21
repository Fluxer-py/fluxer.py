"""Raw gateway event payloads, dispatched as ``on_raw_*`` events.

Raw events fire whether or not the affected entity is cached, mirroring
discord.py. Each one keeps the original payload and, where the library holds
it, the cached entity as it was before the event.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .enums import Status
from .models.presence import CustomStatus

if TYPE_CHECKING:
    from .models.channel import Channel
    from .models.guild import Guild
    from .models.member import GuildMember
    from .models.message import Message
    from .models.user import User


def _maybe_int(value: Any) -> int | None:
    return int(value) if value is not None else None


class RawMessageDeleteEvent:
    """Payload of ``on_raw_message_delete``.

    Attributes:
        message_id: The deleted message's ID.
        channel_id: The channel the message was in.
        guild_id: The guild the channel belongs to, if any.
        cached_message: The message from the cache, or None when it was not cached.
        raw_data: Original payload; excluded from repr.
    """

    message_id: int | None
    channel_id: int | None
    guild_id: int | None

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Parse a Message Delete payload.

        Args:
            data: Message Delete payload.
        """
        self.message_id = _maybe_int(data.get("id"))
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.cached_message: Message | None = None
        self.raw_data: Mapping[str, Any] = data


class RawBulkMessageDeleteEvent:
    """Payload of ``on_raw_bulk_message_delete``.

    Attributes:
        message_ids: The deleted messages' IDs.
        channel_id: The channel the messages were in.
        guild_id: The guild the channel belongs to, if any.
        cached_messages: The deleted messages that were cached.
        raw_data: Original payload; excluded from repr.
    """

    message_ids: list[int]
    channel_id: int | None
    guild_id: int | None

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Parse a Message Delete Bulk payload.

        Args:
            data: Message Delete Bulk payload.
        """
        raw_ids = data.get("ids", data.get("message_ids", []))
        ids = raw_ids if isinstance(raw_ids, Iterable) else []
        self.message_ids = [int(value) for value in ids]
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.cached_messages: list[Message] = []
        self.raw_data: Mapping[str, Any] = data


class RawMessageUpdateEvent:
    """Payload of ``on_raw_message_edit``.

    Attributes:
        message_id: The edited message's ID.
        channel_id: The channel the message is in.
        guild_id: The guild the channel belongs to, if any.
        data: The complete updated message payload.
        message: The updated message.
        cached_message: A copy of the message before the edit, or None when it
            was not cached.
    """

    message_id: int | None
    channel_id: int | None
    guild_id: int | None

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Parse a Message Update payload.

        Args:
            data: Message Update payload.
        """
        self.message_id = _maybe_int(data.get("id"))
        self.channel_id = _maybe_int(data.get("channel_id"))
        self.guild_id = _maybe_int(data.get("guild_id"))
        self.data: Mapping[str, Any] = data
        self.message: Message | None = None
        self.cached_message: Message | None = None


class RawMemberRemoveEvent:
    """Payload of ``on_raw_member_remove``.

    Attributes:
        guild_id: The guild the user left.
        user: The cached member when there was one, otherwise the user. Fluxer
            sends only the user ID, so an uncached user has no other fields.
        raw_data: Original payload; excluded from repr.
    """

    def __init__(self, data: Mapping[str, Any], user: User | GuildMember) -> None:
        """Parse a Guild Member Remove payload.

        Args:
            data: Guild Member Remove payload.
            user: The resolved member or user.
        """
        self.guild_id: int = int(data["guild_id"])
        self.user: User | GuildMember = user
        self.raw_data: Mapping[str, Any] = data


class RawTypingEvent:
    """Payload of ``on_raw_typing``.

    Attributes:
        channel_id: The channel the user is typing in.
        user_id: The user that started typing.
        timestamp: When typing started.
        guild_id: The guild the channel belongs to, if any.
        user: The resolved member or user, or None when it is unknown.
        raw_data: Original payload; excluded from repr.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Parse a Typing Start payload.

        Args:
            data: Typing Start payload.
        """
        self.channel_id: int = int(data["channel_id"])
        self.user_id: int = int(data["user_id"])
        self.timestamp: datetime = datetime.fromtimestamp(
            float(data.get("timestamp", 0)), tz=timezone.utc
        )
        self.guild_id: int | None = _maybe_int(data.get("guild_id"))
        self.user: User | GuildMember | None = None
        self.raw_data: Mapping[str, Any] = data


class RawPresenceUpdateEvent:
    """Payload of ``on_raw_presence_update``.

    Attributes:
        user_id: The user the presence belongs to.
        guild_id: The guild the presence arrived through, if any.
        guild: The cached guild, if any.
        status: The published status.
        raw_status: The published status as the wire string.
        mobile: Whether the active status comes from a mobile session.
        afk: Whether every one of the user's sessions is away.
        custom_status: The user's custom status, or None.
        raw_data: Original payload; excluded from repr.
    """

    def __init__(
        self,
        data: Mapping[str, Any],
        *,
        guild_id: int | None = None,
    ) -> None:
        """Parse a presence object.

        Args:
            data: Presence object.
            guild_id: Guild context for a presence inside Presence Update Bulk.
        """
        self.user_id: int = int(data["user"]["id"])
        self.guild_id: int | None = _maybe_int(data.get("guild_id")) or guild_id
        self.guild: Guild | None = None
        self.raw_status: str = str(data.get("status", "offline"))
        try:
            self.status: Status = Status(self.raw_status)
        except ValueError:
            self.status = Status.offline
        self.mobile: bool = bool(data.get("mobile", False))
        self.afk: bool = bool(data.get("afk", False))
        custom = data.get("custom_status")
        self.custom_status: CustomStatus | None = (
            CustomStatus.from_data(custom) if isinstance(custom, dict) else None
        )
        self.raw_data: Mapping[str, Any] = data


class _RawThreadEvent:
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.thread_id: int = int(data["id"])
        self.thread_type: int | None = data.get("type")
        self.guild_id: int | None = _maybe_int(data.get("guild_id"))
        self.parent_id: int | None = _maybe_int(data.get("parent_id"))
        self.thread: Channel | None = None
        self.raw_data: Mapping[str, Any] = data


class RawThreadUpdateEvent(_RawThreadEvent):
    """Payload of ``on_raw_thread_update``.

    Attributes:
        thread_id: The updated thread's ID.
        thread_type: The thread's channel type.
        guild_id: The thread's guild.
        parent_id: The thread's parent channel.
        thread: The cached thread before the update, or None when it was not cached.
        data: The complete updated thread payload.
        raw_data: Original payload; excluded from repr.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Parse a Thread Update payload.

        Args:
            data: Thread Update payload.
        """
        super().__init__(data)
        self.data: Mapping[str, Any] = data


class RawThreadDeleteEvent(_RawThreadEvent):
    """Payload of ``on_raw_thread_delete``.

    Attributes:
        thread_id: The deleted thread's ID.
        thread_type: The thread's channel type.
        guild_id: The thread's guild.
        parent_id: The thread's parent channel.
        thread: The cached thread, or None when it was not cached.
        raw_data: Original payload; excluded from repr.
    """

    @classmethod
    def _from_thread(cls, thread: Channel) -> RawThreadDeleteEvent:
        event = cls(
            {
                "id": thread.id,
                "type": thread.type,
                "guild_id": thread.guild_id,
                "parent_id": thread.parent_id,
            }
        )
        event.thread = thread
        return event


class RawThreadMembersUpdate:
    """Payload of ``on_raw_thread_member_remove``.

    Attributes:
        thread_id: The thread whose members changed.
        guild_id: The thread's guild.
        member_count: The thread member count, capped at 50 by Fluxer.
        data: The Thread Members Update payload.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        """Parse a Thread Members Update payload.

        Args:
            data: Thread Members Update payload.
        """
        self.thread_id: int = int(data["id"])
        self.guild_id: int | None = _maybe_int(data.get("guild_id"))
        self.member_count: int | None = data.get("member_count")
        self.data: Mapping[str, Any] = data


__all__ = (
    "RawMessageDeleteEvent",
    "RawBulkMessageDeleteEvent",
    "RawMessageUpdateEvent",
    "RawMemberRemoveEvent",
    "RawTypingEvent",
    "RawPresenceUpdateEvent",
    "RawThreadUpdateEvent",
    "RawThreadDeleteEvent",
    "RawThreadMembersUpdate",
)
