"""discord.py-compatible gateway events, their arguments, and their raw variants."""

from datetime import datetime, timezone
from typing import Any

import fluxer

Events = list[tuple[str, tuple[Any, ...]]]


def guild_payload(guild_id: str = "1", **extra: Any) -> dict[str, Any]:
    return {
        "id": guild_id,
        "name": "guild",
        "member_count": 2,
        "roles": [{"id": "4", "name": "mod", "permissions": "0"}],
        "channels": [{"id": "2", "type": 0, "name": "chat"}],
        "emojis": [{"id": "50", "name": "old"}],
        "stickers": [{"id": "60", "name": "old"}],
        "members": [{"user": {"id": "3", "username": "author"}, "roles": []}],
        **extra,
    }


def message_payload(message_id: int = 10, **extra: Any) -> dict[str, Any]:
    return {
        "id": str(message_id),
        "channel_id": "2",
        "guild_id": "1",
        "author": {"id": "3", "username": "author"},
        "content": "hello",
        "timestamp": "2026-01-01T00:00:00Z",
        **extra,
    }


def parse(client: fluxer.Client, name: str, data: Any) -> Events:
    return client._state._parse_dispatch(name, data)


def named(events: Events, name: str) -> list[tuple[Any, ...]]:
    return [args for event, args in events if event == name]


def only(events: Events, name: str) -> tuple[Any, ...]:
    matches = named(events, name)
    assert len(matches) == 1, (name, [event for event, _ in events])
    return matches[0]


def guild_client(**options: Any) -> fluxer.Client:
    client = fluxer.Client(**options)
    parse(client, "GUILD_CREATE", guild_payload())
    return client


def reaction(user: str = "3", name: str = "x", **extra: Any) -> dict[str, Any]:
    return {
        "user_id": user,
        "channel_id": "2",
        "message_id": "10",
        "guild_id": "1",
        "emoji": {"name": name},
        **extra,
    }


def test_reaction_remove_clear_and_clear_emoji() -> None:
    client = guild_client()
    parse(client, "MESSAGE_CREATE", message_payload())
    message = client.get_message(10)
    assert message is not None

    added = parse(client, "MESSAGE_REACTION_ADD", reaction("3"))
    assert [event for event, _ in added] == ["on_raw_reaction_add", "on_reaction_add"]
    parse(client, "MESSAGE_REACTION_ADD", reaction("7"))

    removed = parse(client, "MESSAGE_REACTION_REMOVE", reaction("3"))
    assert only(removed, "on_raw_reaction_remove")[0].event_type == "REACTION_REMOVE"
    item, user = only(removed, "on_reaction_remove")
    assert item.count == 1 and str(item.emoji) == "x"
    assert user is client.get_member(1, 3)

    parse(client, "MESSAGE_REACTION_ADD", reaction("3", "y"))
    cleared_emoji = parse(
        client,
        "MESSAGE_REACTION_REMOVE_EMOJI",
        {
            "channel_id": "2",
            "message_id": "10",
            "guild_id": "1",
            "emoji": {"name": "y"},
        },
    )
    assert only(cleared_emoji, "on_raw_reaction_clear_emoji")[0].message_id == 10
    assert str(only(cleared_emoji, "on_reaction_clear_emoji")[0].emoji) == "y"
    assert [str(r.emoji) for r in message.reactions] == ["x"]

    cleared = parse(
        client,
        "MESSAGE_REACTION_REMOVE_ALL",
        {"channel_id": "2", "message_id": "10", "guild_id": "1"},
    )
    cleared_message, old = only(cleared, "on_reaction_clear")
    assert cleared_message is message and [str(r.emoji) for r in old] == ["x"]
    assert message.reactions == []

    # Uncached messages only produce raw events, like discord.py.
    uncached = reaction("3", message_id="999")
    assert [e for e, _ in parse(client, "MESSAGE_REACTION_REMOVE", uncached)] == [
        "on_raw_reaction_remove"
    ]
    missing = parse(client, "MESSAGE_REACTION_REMOVE", reaction("3", "never"))
    assert [e for e, _ in missing] == ["on_raw_reaction_remove"]


def test_message_edit_delete_and_bulk_delete() -> None:
    client = guild_client()
    parse(client, "MESSAGE_CREATE", message_payload(10))
    parse(client, "MESSAGE_CREATE", message_payload(11))
    parse(client, "MESSAGE_CREATE", message_payload(12))

    edited = parse(client, "MESSAGE_UPDATE", message_payload(10, content="edited"))
    raw = only(edited, "on_raw_message_edit")[0]
    before, after = only(edited, "on_message_edit")
    assert before.content == "hello" and after.content == "edited"
    assert after is client.get_message(10) and raw.message is after
    assert raw.cached_message is before and raw.message_id == 10

    uncached = parse(client, "MESSAGE_UPDATE", message_payload(99))
    assert [e for e, _ in uncached] == ["on_raw_message_edit"]
    assert only(uncached, "on_raw_message_edit")[0].cached_message is None

    deleted = parse(client, "MESSAGE_DELETE", {"id": "10", "channel_id": "2"})
    assert only(deleted, "on_message_delete")[0] is after
    assert only(deleted, "on_raw_message_delete")[0].cached_message is after
    gone = parse(client, "MESSAGE_DELETE", {"id": "10", "channel_id": "2"})
    assert [e for e, _ in gone] == ["on_raw_message_delete"]

    payload = {"ids": ["11", "12", "404"], "channel_id": "2", "guild_id": "1"}
    bulk = parse(client, "MESSAGE_DELETE_BULK", payload)
    messages = only(bulk, "on_bulk_message_delete")[0]
    assert sorted(m.id for m in messages) == [11, 12]
    raw_bulk = only(bulk, "on_raw_bulk_message_delete")[0]
    assert raw_bulk.message_ids == [11, 12, 404] and len(raw_bulk.cached_messages) == 2
    assert only(bulk, "on_message_delete_bulk")[0] is payload


def test_bot_guild_join_available_unavailable_update_and_remove() -> None:
    client = fluxer.Client()
    parse(
        client,
        "READY",
        {
            "session_id": "s",
            "user": {"id": "99", "username": "bot", "bot": True},
            "guilds": [{"id": "1", "unavailable": True}],
        },
    )
    burst = parse(client, "GUILD_CREATE", guild_payload(unavailable=False))
    guild = only(burst, "on_guild_available")[0]
    assert guild is client.get_guild(1) and not guild.unavailable

    joined = parse(client, "GUILD_CREATE", guild_payload("5"))
    assert only(joined, "on_guild_join")[0].id == 5

    updated = parse(client, "GUILD_UPDATE", {"id": "1", "name": "renamed"})
    before, after = only(updated, "on_guild_update")
    assert before.name == "guild" and after.name == "renamed" and after is guild
    assert "on_guild_unavailable" not in [e for e, _ in updated]

    went_away = parse(client, "GUILD_DELETE", {"id": "1", "unavailable": True})
    assert only(went_away, "on_guild_unavailable")[0] is guild
    # A second notice for an already unavailable guild is not repeated.
    assert parse(client, "GUILD_DELETE", {"id": "1", "unavailable": True}) == []

    back = parse(client, "GUILD_CREATE", guild_payload(unavailable=False))
    assert only(back, "on_guild_available")[0] is guild

    removed = parse(client, "GUILD_DELETE", {"id": "1"})
    assert only(removed, "on_guild_remove")[0] is guild
    assert client.get_guild(1) is None
    assert parse(client, "GUILD_DELETE", {"id": "404"}) == []


def test_user_session_guild_create_uses_cache_to_tell_join_from_recovery() -> None:
    client = fluxer.Client()
    parse(
        client,
        "READY",
        {
            "session_id": "s",
            "user": {"id": "99", "username": "me"},
            "guilds": [guild_payload()],
        },
    )
    parse(client, "GUILD_UPDATE", {"id": "1", "features": ["UNAVAILABLE_FOR_EVERYONE"]})
    assert only(parse(client, "GUILD_CREATE", guild_payload()), "on_guild_available")
    assert only(parse(client, "GUILD_CREATE", guild_payload("7")), "on_guild_join")


def test_guild_update_into_unavailable_dispatches_unavailable() -> None:
    client = guild_client()
    events = parse(
        client, "GUILD_UPDATE", {"id": "1", "features": ["UNAVAILABLE_FOR_EVERYONE"]}
    )
    assert only(events, "on_guild_unavailable")[0] is client.get_guild(1)


def test_channel_events_guild_private_pins_and_bulk() -> None:
    client = guild_client()
    created = parse(
        client,
        "CHANNEL_CREATE",
        {"id": "20", "guild_id": "1", "type": 0, "name": "new"},
    )
    channel = only(created, "on_guild_channel_create")[0]
    assert only(created, "on_channel_create")[0] is channel

    updated = parse(
        client,
        "CHANNEL_UPDATE",
        {"id": "20", "guild_id": "1", "type": 0, "name": "renamed"},
    )
    before, after = only(updated, "on_guild_channel_update")
    assert (before.name, after.name) == ("new", "renamed") and after is channel
    assert only(updated, "on_channel_update")[0] is channel

    bulk = parse(
        client,
        "CHANNEL_UPDATE_BULK",
        {
            "guild_id": "1",
            "channels": [{"id": "20", "type": 0, "name": "moved", "position": 3}],
        },
    )
    before, after = only(bulk, "on_guild_channel_update")
    assert (before.position, after.position) == (None, 3)

    pins = parse(
        client,
        "CHANNEL_PINS_UPDATE",
        {
            "channel_id": "20",
            "guild_id": "1",
            "last_pin_timestamp": "2026-01-02T03:04:05Z",
        },
    )
    pinned_channel, last_pin = only(pins, "on_guild_channel_pins_update")
    assert pinned_channel is channel
    assert last_pin == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert only(pins, "on_channel_pins_update")[0]["channel_id"] == "20"

    group = parse(client, "CHANNEL_CREATE", {"id": "30", "type": 3, "name": "group"})
    assert [e for e, _ in group] == ["on_channel_create"]
    renamed = parse(
        client, "CHANNEL_UPDATE", {"id": "30", "type": 3, "name": "renamed"}
    )
    before, after = only(renamed, "on_private_channel_update")
    assert (before.name, after.name) == ("group", "renamed")
    dm_pins = parse(
        client, "CHANNEL_PINS_UPDATE", {"channel_id": "30", "last_pin_timestamp": None}
    )
    assert only(dm_pins, "on_private_channel_pins_update") == (after, None)

    deleted = parse(client, "CHANNEL_DELETE", {"id": "20", "guild_id": "1", "type": 0})
    assert only(deleted, "on_guild_channel_delete")[0] is channel
    assert client.get_channel(20) is None


def test_member_join_update_user_update_remove_and_bans() -> None:
    client = guild_client()
    guild = client.get_guild(1)
    assert guild is not None

    joined = parse(
        client,
        "GUILD_MEMBER_ADD",
        {"guild_id": "1", "user": {"id": "8", "username": "new"}, "roles": []},
    )
    member = only(joined, "on_member_join")[0]
    assert isinstance(member, fluxer.GuildMember) and member is guild.get_member(8)
    assert guild.member_count == 3

    payload = {
        "guild_id": "1",
        "user": {"id": "8", "username": "renamed"},
        "nick": "nick",
        "roles": [],
    }
    updated = parse(client, "GUILD_MEMBER_UPDATE", payload)
    before, after = only(updated, "on_member_update")
    assert (before.nick, after.nick) == (None, "nick") and after is member
    old_user, new_user = only(updated, "on_user_update")
    assert (old_user.username, new_user.username) == ("new", "renamed")
    assert only(updated, "on_guild_member_update")[0] is payload
    unchanged = parse(client, "GUILD_MEMBER_UPDATE", payload)
    assert "on_user_update" not in [e for e, _ in unchanged]

    banned = parse(client, "GUILD_BAN_ADD", {"guild_id": "1", "user": {"id": "8"}})
    assert only(banned, "on_member_ban") == (guild, member)
    removed = parse(
        client, "GUILD_MEMBER_REMOVE", {"guild_id": "1", "user": {"id": "8"}}
    )
    assert only(removed, "on_member_remove")[0] is member
    raw = only(removed, "on_raw_member_remove")[0]
    assert raw.guild_id == 1 and raw.user is member
    unbanned = parse(client, "GUILD_BAN_REMOVE", {"guild_id": "1", "user": {"id": "8"}})
    unbanned_guild, user = only(unbanned, "on_member_unban")
    assert unbanned_guild is guild and user.id == 8

    stranger = parse(
        client, "GUILD_MEMBER_REMOVE", {"guild_id": "1", "user": {"id": "77"}}
    )
    assert [e for e, _ in stranger] == ["on_raw_member_remove"]
    assert only(stranger, "on_raw_member_remove")[0].user.id == 77


def test_member_events_need_member_retention_for_before_state() -> None:
    client = guild_client(cache_members=False)
    payload = {"guild_id": "1", "user": {"id": "8", "username": "x"}, "roles": []}
    assert only(parse(client, "GUILD_MEMBER_ADD", payload), "on_member_join")[0].id == 8
    assert "on_member_update" not in [
        e for e, _ in parse(client, "GUILD_MEMBER_UPDATE", payload)
    ]


def test_role_emoji_and_sticker_events() -> None:
    client = guild_client()
    guild = client.get_guild(1)
    assert guild is not None

    created = parse(
        client,
        "GUILD_ROLE_CREATE",
        {"guild_id": "1", "role": {"id": "5", "name": "new"}},
    )
    role = only(created, "on_guild_role_create")[0]
    assert role is guild.get_role(5)
    assert named(created, "on_fluxer_event")

    updated = parse(
        client,
        "GUILD_ROLE_UPDATE",
        {"guild_id": "1", "role": {"id": "5", "name": "renamed"}},
    )
    before, after = only(updated, "on_guild_role_update")
    assert (before.name, after.name) == ("new", "renamed") and after is role

    bulk = parse(
        client,
        "GUILD_ROLE_UPDATE_BULK",
        {
            "guild_id": "1",
            "roles": [{"id": "4", "position": 2}, {"id": "5", "position": 1}],
        },
    )
    assert len(named(bulk, "on_guild_role_update")) == 2

    deleted = parse(client, "GUILD_ROLE_DELETE", {"guild_id": "1", "role_id": "5"})
    assert only(deleted, "on_guild_role_delete")[0] is role
    assert (
        parse(client, "GUILD_ROLE_DELETE", {"guild_id": "1", "role_id": "5"})[0][0]
        == "on_fluxer_event"
    )

    emojis = parse(
        client,
        "GUILD_EMOJIS_UPDATE",
        {"guild_id": "1", "emojis": [{"id": "50", "name": "new"}]},
    )
    emoji_guild, before_emojis, after_emojis = only(emojis, "on_guild_emojis_update")
    assert emoji_guild is guild
    assert [e.name for e in before_emojis] == ["old"] and [
        e.name for e in after_emojis
    ] == ["new"]

    stickers = parse(client, "GUILD_STICKERS_UPDATE", {"guild_id": "1", "stickers": []})
    _, before_stickers, after_stickers = only(stickers, "on_guild_stickers_update")
    assert [s.name for s in before_stickers] == ["old"] and after_stickers == []


def test_presence_update_user_update_and_bulk() -> None:
    client = guild_client()
    member = client.get_member(1, 3)
    assert member is not None and member.status is fluxer.Status.offline
    presence = {
        "user": {"id": "3", "username": "renamed"},
        "status": "dnd",
        "mobile": False,
        "afk": False,
        "custom_status": {"text": "busy", "emoji_name": "x", "emoji_animated": False},
        "guild_id": "1",
    }
    events = parse(client, "PRESENCE_UPDATE", presence)
    raw = only(events, "on_raw_presence_update")[0]
    assert raw.status is fluxer.Status.dnd and raw.guild is client.get_guild(1)
    before, after = only(events, "on_presence_update")
    assert before.status is fluxer.Status.offline and after.status is fluxer.Status.dnd
    assert (
        after is member and after.activity is not None and after.activity.name == "busy"
    )
    assert after.custom_status is not None and after.custom_status.text == "busy"
    old_user, new_user = only(events, "on_user_update")
    assert (old_user.username, new_user.username) == ("author", "renamed")

    elsewhere = parse(client, "PRESENCE_UPDATE", {**presence, "guild_id": "404"})
    assert [e for e, _ in elsewhere] == ["on_raw_presence_update", "on_fluxer_event"]

    bulk = parse(
        client,
        "PRESENCE_UPDATE_BULK",
        {
            "guild_id": "1",
            "presences": [{"user": {"id": "3"}, "status": "idle", "mobile": True}],
        },
    )
    assert "on_presence_update" not in [e for e, _ in bulk]
    assert member.status is fluxer.Status.idle and member.is_on_mobile()


def test_current_user_update_reports_changes_only() -> None:
    client = fluxer.Client()
    parse(
        client,
        "READY",
        {"session_id": "s", "user": {"id": "99", "username": "me"}, "guilds": []},
    )
    changed = parse(client, "USER_UPDATE", {"id": "99", "username": "new"})
    before, after = only(changed, "on_user_update")
    assert (before.username, after.username) == ("me", "new") and after is client.user
    same = parse(client, "USER_UPDATE", {"id": "99", "username": "new"})
    assert [e for e, _ in same] == ["on_fluxer_event"]


def test_typing_events() -> None:
    client = guild_client()
    payload = {
        "channel_id": "2",
        "guild_id": "1",
        "user_id": "9",
        "timestamp": 1767225600,
        "member": {"user": {"id": "9", "username": "typer"}, "roles": []},
    }
    events = parse(client, "TYPING_START", payload)
    channel, user, when = only(events, "on_typing")
    assert channel is client.get_channel(2) and user is client.get_member(1, 9)
    assert when == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert only(events, "on_raw_typing")[0].user is user
    assert only(events, "on_typing_start")[0] is payload

    unknown = parse(client, "TYPING_START", {**payload, "channel_id": "404"})
    assert "on_typing" not in [e for e, _ in unknown]


def test_voice_state_update_member_before_after() -> None:
    client = guild_client()
    voice = {
        "guild_id": "1",
        "channel_id": "2",
        "user_id": "3",
        "connection_id": "a",
        "member": {"user": {"id": "3", "username": "author"}, "roles": []},
        "version": 1,
    }
    joined = parse(client, "VOICE_STATE_UPDATE", voice)
    member, before, after = only(joined, "on_voice_state_update")
    assert member is client.get_member(1, 3)
    assert before.channel_id is None and after.channel_id == 2

    muted = parse(
        client, "VOICE_STATE_UPDATE", {**voice, "self_mute": True, "version": 2}
    )
    _, before, after = only(muted, "on_voice_state_update")
    assert (before.self_mute, after.self_mute) == (False, True)

    left = parse(
        client, "VOICE_STATE_UPDATE", {**voice, "channel_id": None, "version": 3}
    )
    _, before, after = only(left, "on_voice_state_update")
    assert before.channel_id == 2 and after.channel_id is None

    assert parse(client, "VOICE_STATE_UPDATE", {**voice, "version": 2}) == []
    call = {"guild_id": None, "channel_id": "30", "user_id": "3", "connection_id": "c"}
    assert parse(client, "VOICE_STATE_UPDATE", call) == []


def test_webhooks_invites_and_audit_log_entries() -> None:
    client = guild_client()
    webhooks = parse(client, "WEBHOOKS_UPDATE", {"guild_id": "1", "channel_id": "2"})
    assert only(webhooks, "on_webhooks_update")[0] is client.get_channel(2)
    assert not named(webhooks, "on_webhooks_update_data")

    created = parse(
        client,
        "INVITE_CREATE",
        {"code": "abc", "guild_id": "1", "channel_id": "2", "uses": 0},
    )
    invite = only(created, "on_invite_create")[0]
    assert (
        isinstance(invite, fluxer.Invite)
        and invite.code == "abc"
        and invite.channel_id == 2
    )
    deleted = parse(client, "INVITE_DELETE", {"code": "abc", "guild_id": "1"})
    assert only(deleted, "on_invite_delete")[0].code == "abc"

    entry_payload = {
        "id": "70",
        "guild_id": "1",
        "action_type": 1,
        "user_id": "3",
        "target_id": "1",
    }
    entry = only(
        parse(client, "GUILD_AUDIT_LOG_ENTRY_CREATE", entry_payload),
        "on_audit_log_entry_create",
    )[0]
    assert (
        isinstance(entry, fluxer.AuditLogEntry)
        and entry.guild_id == 1
        and entry.id == 70
    )


def thread_payload(thread_id: str = "40", **extra: Any) -> dict[str, Any]:
    return {
        "id": thread_id,
        "type": 11,
        "guild_id": "1",
        "parent_id": "2",
        "owner_id": "3",
        "name": "thread",
        "thread_metadata": {
            "archived": False,
            "auto_archive_duration": 4320,
            "locked": False,
        },
        "member_count": 1,
        **extra,
    }


def test_thread_create_join_update_delete_and_cache() -> None:
    client = fluxer.Client()
    parse(
        client,
        "READY",
        {
            "session_id": "s",
            "user": {"id": "99", "username": "bot", "bot": True},
            "guilds": [],
        },
    )
    parse(client, "GUILD_CREATE", guild_payload(threads=[thread_payload("41")]))
    guild = client.get_guild(1)
    assert guild is not None and guild.get_thread(41) is not None
    assert [c.id for c in guild.channels] == [2] and client.get_channel(41) is not None

    created = parse(client, "THREAD_CREATE", thread_payload(newly_created=True))
    thread = only(created, "on_thread_create")[0]
    assert thread.is_thread and thread is guild.get_thread(40)
    assert thread.parent is guild.get_channel(2) and thread.me is None
    # A thread that is already cached produces no second create or join.
    again = parse(client, "THREAD_CREATE", thread_payload(newly_created=True))
    assert [event for event, _ in again] == ["on_fluxer_event"]

    joined = parse(
        client,
        "THREAD_CREATE",
        thread_payload(
            "42", member={"join_timestamp": "2026-01-01T00:00:00Z", "flags": 0}
        ),
    )
    joined_thread = only(joined, "on_thread_join")[0]
    assert joined_thread.me is not None and joined_thread.me.id == 99

    updated = parse(client, "THREAD_UPDATE", thread_payload(name="renamed"))
    raw = only(updated, "on_raw_thread_update")[0]
    before, after = only(updated, "on_thread_update")
    assert (before.name, after.name) == ("thread", "renamed") and after is thread
    assert raw.thread is thread and raw.thread_id == 40

    archived = parse(
        client,
        "THREAD_UPDATE",
        thread_payload("41", thread_metadata={"archived": True, "locked": False}),
    )
    assert only(archived, "on_thread_update")[1].archived
    assert guild.get_thread(41) is None and client.get_channel(41) is None

    deleted = parse(
        client,
        "THREAD_DELETE",
        {"id": "40", "guild_id": "1", "parent_id": "2", "type": 11},
    )
    assert only(deleted, "on_raw_thread_delete")[0].thread is thread
    assert only(deleted, "on_thread_delete")[0] is thread
    assert guild.get_thread(40) is None
    uncached = parse(
        client,
        "THREAD_DELETE",
        {"id": "40", "guild_id": "1", "parent_id": "2", "type": 11},
    )
    assert only(uncached, "on_raw_thread_delete")[0].thread is None
    assert not named(uncached, "on_thread_delete")

    cascade = parse(client, "CHANNEL_DELETE", {"id": "2", "guild_id": "1", "type": 0})
    assert [t.id for (t,) in named(cascade, "on_thread_delete")] == [42]
    assert named(cascade, "on_raw_thread_delete")[0][0].thread_id == 42
    assert guild.get_thread(42) is None


def test_thread_members_and_list_sync() -> None:
    client = fluxer.Client()
    parse(
        client,
        "READY",
        {
            "session_id": "s",
            "user": {"id": "99", "username": "bot", "bot": True},
            "guilds": [],
        },
    )
    parse(client, "GUILD_CREATE", guild_payload())
    thread = only(
        parse(client, "THREAD_CREATE", thread_payload(newly_created=True)),
        "on_thread_create",
    )[0]

    added = parse(
        client,
        "THREAD_MEMBERS_UPDATE",
        {
            "id": "40",
            "guild_id": "1",
            "member_count": 2,
            "added_members": [
                {
                    "id": "40",
                    "user_id": "3",
                    "join_timestamp": "2026-01-01T00:00:00Z",
                    "flags": 0,
                    "member": {"roles": []},
                    "presence": {"user": {"id": "3"}, "status": "online"},
                },
                {
                    "id": "40",
                    "user_id": "99",
                    "join_timestamp": "2026-01-01T00:00:00Z",
                    "flags": 0,
                },
            ],
        },
    )
    thread_member = only(added, "on_thread_member_join")[0]
    assert thread_member.id == 3 and thread_member.thread is thread
    assert thread_member.member is client.get_member(1, 3)
    assert thread_member.member.status is fluxer.Status.online
    assert only(added, "on_thread_join")[0] is thread and thread.me is not None
    assert thread.member_count == 2 and thread.thread_members == [thread_member]

    removed = parse(
        client,
        "THREAD_MEMBERS_UPDATE",
        {
            "id": "40",
            "guild_id": "1",
            "member_count": 0,
            "removed_member_ids": ["3", "99"],
        },
    )
    assert only(removed, "on_raw_thread_member_remove")[0].thread_id == 40
    assert only(removed, "on_thread_member_remove")[0] is thread_member
    assert only(removed, "on_thread_remove")[0] is thread and thread.me is None

    synced = parse(
        client,
        "THREAD_LIST_SYNC",
        {
            "guild_id": "1",
            "threads": [thread_payload("43")],
            "members": [{"id": "43", "flags": 0}],
        },
    )
    assert only(synced, "on_thread_join")[0].id == 43
    assert only(synced, "on_thread_remove")[0] is thread
    synced_thread = client.get_guild(1).get_thread(43)  # type: ignore[union-attr]
    assert synced_thread is not None and synced_thread.me is not None


def test_thread_join_for_cached_and_created_threads() -> None:
    client = fluxer.Client()
    parse(
        client,
        "READY",
        {"session_id": "s", "user": {"id": "99", "username": "me"}, "guilds": []},
    )
    parse(client, "GUILD_CREATE", guild_payload(threads=[thread_payload("20")]))
    me = {
        "id": "20",
        "user_id": "99",
        "join_timestamp": "2026-01-01T00:00:00Z",
        "flags": 0,
    }
    members_update = {
        "id": "20",
        "guild_id": "1",
        "member_count": 1,
        "added_members": [me],
    }

    # Joining a thread that is already cached reports exactly one join.
    joined = parse(client, "THREAD_CREATE", thread_payload("20", member=me))
    assert len(named(joined, "on_thread_join")) == 1
    assert not named(
        parse(client, "THREAD_MEMBERS_UPDATE", members_update), "on_thread_join"
    )

    # Leaving and rejoining reports the rejoin.
    left = parse(
        client,
        "THREAD_MEMBERS_UPDATE",
        {"id": "20", "guild_id": "1", "removed_member_ids": ["99"]},
    )
    assert named(left, "on_thread_remove")
    rejoined = parse(client, "THREAD_CREATE", thread_payload("20", member=me))
    assert len(named(rejoined, "on_thread_join")) == 1

    # A thread the session creates is both created and joined, as in discord.py.
    mine = {**me, "id": "21"}
    created = parse(
        client, "THREAD_CREATE", thread_payload("21", newly_created=True, member=mine)
    )
    assert [e for e, _ in created if e != "on_fluxer_event"] == [
        "on_thread_create",
        "on_thread_join",
    ]


def test_uncaching_a_thread_keeps_its_cached_messages() -> None:
    client = guild_client()
    parse(client, "THREAD_CREATE", thread_payload("20", newly_created=True))
    parse(client, "MESSAGE_CREATE", message_payload(500, channel_id="20"))
    archived = thread_payload("20", thread_metadata={"archived": True, "locked": False})
    parse(client, "THREAD_UPDATE", archived)
    assert client.get_channel(20) is None and client.get_message(500) is not None
    deleted = parse(client, "MESSAGE_DELETE", {"id": "500", "channel_id": "20"})
    assert named(deleted, "on_message_delete")

    parse(client, "THREAD_CREATE", thread_payload("21", newly_created=True))
    parse(client, "MESSAGE_CREATE", message_payload(501, channel_id="21"))
    parse(client, "THREAD_LIST_SYNC", {"guild_id": "1", "threads": [], "members": []})
    assert client.get_channel(21) is None and client.get_message(501) is not None

    parse(client, "THREAD_CREATE", thread_payload("22", newly_created=True))
    parse(client, "MESSAGE_CREATE", message_payload(502, channel_id="22"))
    parse(
        client,
        "THREAD_DELETE",
        {"id": "22", "guild_id": "1", "parent_id": "2", "type": 11},
    )
    assert client.get_message(502) is None


def test_presence_update_still_reaches_on_fluxer_event() -> None:
    client = guild_client()
    presence = {"user": {"id": "3"}, "status": "online", "guild_id": "1"}
    assert named(parse(client, "PRESENCE_UPDATE", presence), "on_fluxer_event")
    assert named(
        parse(client, "PRESENCE_UPDATE", {**presence, "guild_id": "9"}),
        "on_fluxer_event",
    )
