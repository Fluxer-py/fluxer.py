"""Thread metadata and thread membership models.

A Fluxer thread is a channel object, so threads use the unified
:class:`~fluxer.models.channel.Channel` model. This module holds the two
thread-specific sub-objects: the archive state and a user's membership.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from ..utils import _try_parse_time as parse_time

if TYPE_CHECKING:
    from ..state import ConnectionState
    from .channel import Channel
    from .member import GuildMember


ThreadArchiveDuration = Literal[60, 1440, 4320, 10080]
"""Minutes of inactivity before a thread archives: 1 hour, 1 day, 3 days or 1 week."""


def _maybe_int(value: Any) -> int | None:
    return int(value) if value is not None else None


@dataclass(slots=True)
class ThreadMetadata:
    """Archive and lock state of a thread.

    Attributes:
        archived: Whether the thread is archived.
        auto_archive_duration: Minutes of inactivity before the thread archives.
        archive_timestamp: When the thread was last archived, unarchived, or given
            a new auto archive duration.
        locked: Whether only thread moderators can act in the thread.
        invitable: Whether non-moderators can add members, present only on a
            private thread.
        create_timestamp: When the thread was created.
    """

    archived: bool = False
    auto_archive_duration: int | None = None
    archive_timestamp: datetime | None = None
    locked: bool = False
    invitable: bool | None = None
    create_timestamp: datetime | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> ThreadMetadata:
        """Build thread metadata from its decoded payload.

        Args:
            data: Thread metadata object.

        Returns:
            The parsed metadata.
        """
        return cls(
            archived=bool(data.get("archived", False)),
            auto_archive_duration=data.get("auto_archive_duration"),
            archive_timestamp=parse_time(data.get("archive_timestamp")),
            locked=bool(data.get("locked", False)),
            invitable=data.get("invitable"),
            create_timestamp=parse_time(data.get("create_timestamp")),
        )


@dataclass(slots=True)
class ThreadMember:
    """A user's membership in a thread.

    As in discord.py, ``id`` is the member's user ID. Fluxer's own thread member
    object names the thread ``id`` and the user ``user_id``; both are mapped here.

    Attributes:
        id: The ID of the user.
        thread_id: The ID of the thread.
        joined_at: When the user last joined the thread.
        flags: Thread member flags.
        muted: Whether the user muted the thread, present only on the current
            user's own membership.
        mute_config: The stored mute expiry, present only on the current user's
            own membership.
        guild_id: The ID of the thread's guild, when known.
        thread: The cached thread channel, when available.
        member: The guild member behind this membership, when available.
        raw_data: Original payload; excluded from repr.
    """

    id: int
    thread_id: int
    joined_at: datetime | None = None
    flags: int = 0
    muted: bool | None = None
    mute_config: dict[str, Any] | None = None
    guild_id: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)
    _member: GuildMember | None = field(default=None, repr=False, compare=False)
    _state: ConnectionState | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        *,
        thread_id: int | None = None,
        user_id: int | None = None,
        guild_id: int | None = None,
        state: ConnectionState | None = None,
    ) -> ThreadMember:
        """Build a thread member from its decoded payload.

        Args:
            data: Thread member object.
            thread_id: Thread ID for payloads that omit ``id``.
            user_id: User ID for payloads that omit ``user_id``.
            guild_id: Guild ID for payloads that omit ``guild_id``.
            state: Live state used to resolve the thread and guild member.

        Returns:
            The parsed thread member.
        """
        resolved_user = _maybe_int(data.get("user_id")) or user_id
        resolved_thread = _maybe_int(data.get("id")) or thread_id
        if resolved_user is None or resolved_thread is None:
            raise ValueError("A thread member needs both a user ID and a thread ID")
        return cls(
            id=resolved_user,
            thread_id=resolved_thread,
            joined_at=parse_time(data.get("join_timestamp")),
            flags=int(data.get("flags", 0) or 0),
            muted=data.get("muted"),
            mute_config=data.get("mute_config"),
            guild_id=_maybe_int(data.get("guild_id")) or guild_id,
            raw_data=data,
            _state=state,
        )

    @property
    def thread(self) -> Channel | None:
        """The cached thread this membership belongs to.

        Returns:
            The thread channel, or None when it is not cached.
        """
        if self._state is None:
            return None
        return self._state.channels.get(self.thread_id)

    @property
    def member(self) -> GuildMember | None:
        """The guild member behind this membership.

        Returns:
            The member from the payload or the member cache, or None.
        """
        if self._member is not None:
            return self._member
        if self._state is None:
            return None
        return self._state.get_member(self.guild_id, self.id)

    @property
    def mention(self) -> str:
        """Mention string for the member's user.

        Returns:
            The ``<@id>`` mention.
        """
        return f"<@{self.id}>"


__all__ = ("ThreadArchiveDuration", "ThreadMember", "ThreadMetadata")
