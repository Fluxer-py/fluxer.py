---
icon: lucide/radio
---

# Events

Event names and arguments follow discord.py 2.x wherever Fluxer has the same
concept, so handlers written for discord.py keep working. Register them the usual
ways:

```py
@bot.event
async def on_message_edit(before, after):
    ...

@bot.listen("on_reaction_remove")
async def log_reaction(reaction, user):
    ...

class Logs(commands.Cog):
    @commands.Cog.listener()
    async def on_member_join(self, member):
        ...
```

`bot.wait_for("reaction_add", check=...)` works with every event below, and so
does a manual `bot.dispatch("on_<name>", ...)`.

## How the cache affects events

Like discord.py, some events need the affected object to be cached:

- `on_message_edit` and `on_message_delete` fire only for messages in the message
  cache, which holds the last `max_messages` messages. The `on_raw_*` variants
  always fire.
- `on_member_update` and `on_presence_update` need the member to be cached, which
  `cache_members=False` turns off.
- `on_reaction_add`, `on_reaction_remove`, `on_reaction_clear` and
  `on_reaction_clear_emoji` need the message to be cached.

`before` arguments are shallow snapshots taken just before the update, as in
discord.py.

## Connection

| Event | Arguments | Notes |
| --- | --- | --- |
| `on_connect` | none | The gateway socket opened. Fires again after every reconnect. |
| `on_disconnect` | none | The gateway socket closed, for any reason. |
| `on_ready` | none | The session is ready. See the note below. |
| `on_resumed` | none | A dropped session resumed. |
| `on_error` | `event_method, *args` | An event handler raised. `sys.exc_info()` holds the error. |

`on_ready` fires as soon as Fluxer sends Ready. For a bot, every guild is still
unavailable at that point, and each one then arrives as `on_guild_available`.
discord.py instead waits for that burst before firing `on_ready`. If your
`on_ready` reads guild data, use `on_guild_available` for it instead.

Without any `on_error` handler, errors are logged. Overriding `Client.on_error`
in a subclass replaces that default.

## Guilds

| Event | Arguments | Notes |
| --- | --- | --- |
| `on_guild_join` | `guild` | The bot joined a guild. |
| `on_guild_remove` | `guild` | The bot left or was removed from a guild. |
| `on_guild_available` | `guild` | A guild became available, including each guild after `on_ready`. |
| `on_guild_unavailable` | `guild` | An available guild became unavailable. |
| `on_guild_update` | `before, after` | The guild's settings changed. |
| `on_guild_emojis_update` | `guild, before, after` | Lists of emojis. |
| `on_guild_stickers_update` | `guild, before, after` | Lists of stickers. |
| `on_guild_role_create` | `role` | |
| `on_guild_role_update` | `before, after` | Also fires once per role when roles are reordered. |
| `on_guild_role_delete` | `role` | |
| `on_audit_log_entry_create` | `entry` | An `AuditLogEntry`. Needs `VIEW_AUDIT_LOG`. |
| `on_invite_create` | `invite` | An `Invite`. Needs `MANAGE_CHANNELS` on the channel. |
| `on_invite_delete` | `invite` | An `Invite` with only `code`, `channel_id` and `guild_id` set. |
| `on_webhooks_update` | `channel` | The channel's webhooks changed. Fetch them to see how. |

## Channels and threads

Threads, forum channels and media channels are all `Channel` objects. A thread
has `is_thread`, `archived`, `locked`, `parent`, `me` and `thread_members`.
Active threads are cached in `guild.threads` and `client.get_channel()`, but not
in `guild.channels`, as in discord.py. Starting, editing and listing threads is
covered on the [Threads](threads.md) page.

| Event | Arguments | Notes |
| --- | --- | --- |
| `on_guild_channel_create` | `channel` | |
| `on_guild_channel_update` | `before, after` | Also fires once per channel when channels are reordered. |
| `on_guild_channel_delete` | `channel` | |
| `on_guild_channel_pins_update` | `channel, last_pin` | `last_pin` is a `datetime` or `None`. |
| `on_private_channel_update` | `before, after` | Group DMs only. |
| `on_private_channel_pins_update` | `channel, last_pin` | |
| `on_thread_create` | `thread` | A new thread was created. |
| `on_thread_join` | `thread` | The bot joined or gained access to an existing thread. |
| `on_thread_update` | `before, after` | Archived threads leave the cache after this event. |
| `on_thread_delete` | `thread` | Also fires for each thread of a deleted channel. |
| `on_thread_remove` | `thread` | The bot left or lost access to a thread. |
| `on_thread_member_join` | `member` | A `ThreadMember`. |
| `on_thread_member_remove` | `member` | Only for members seen joining since the thread was cached. |
| `on_raw_thread_update` | `payload` | `RawThreadUpdateEvent`, cached or not. |
| `on_raw_thread_delete` | `payload` | `RawThreadDeleteEvent`, cached or not. |
| `on_raw_thread_member_remove` | `payload` | `RawThreadMembersUpdate`. |

`ThreadMember.id` is the user's ID, as in discord.py, and `ThreadMember.member`
is their `GuildMember` when known. Fluxer does not send a thread's full member
list on connect, so `thread.thread_members` grows from join events only.

User accounts receive thread events only when they identify with Fluxer's
`CHANNEL_THREADS` session flag, which fluxer.py does not send yet. Bots always
receive them.

## Members and users

| Event | Arguments | Notes |
| --- | --- | --- |
| `on_member_join` | `member` | |
| `on_member_remove` | `member` | Only when the member was cached. |
| `on_raw_member_remove` | `payload` | `RawMemberRemoveEvent`. `payload.user` is the cached member, or else a `User` that may hold only `id`. |
| `on_member_update` | `before, after` | Nickname, roles, timeout, guild avatar and other member fields. |
| `on_user_update` | `before, after` | A user's name, avatar or other profile fields changed. Also fires for the bot's own account. |
| `on_member_ban` | `guild, user` | The cached `GuildMember`, or else a `User` that may hold only `id`. |
| `on_member_unban` | `guild, user` | A `User`. |
| `on_presence_update` | `before, after` | Members whose status or custom status changed. |
| `on_raw_presence_update` | `payload` | `RawPresenceUpdateEvent`, for every presence. |

Fluxer presences have a status and a custom status, and no rich activities.
`member.status` is a `Status`, `member.custom_status` is a `CustomStatus`, and
`member.activity` returns the custom status as a `CustomActivity` so
discord.py-style checks keep working. Fluxer also reports
`member.is_on_mobile()` and `member.is_afk()`.

Bots receive presences only for members they subscribed to through a lazy
member request. Presences that arrive in bulk when a guild recovers update the
cache without firing `on_presence_update`.

## Messages and reactions

| Event | Arguments | Notes |
| --- | --- | --- |
| `on_message` | `message` | |
| `on_message_edit` | `before, after` | Cached messages only. |
| `on_message_delete` | `message` | Cached messages only. |
| `on_bulk_message_delete` | `messages` | The cached messages among those deleted. |
| `on_raw_message_edit` | `payload` | `RawMessageUpdateEvent` with `message` and `cached_message`. |
| `on_raw_message_delete` | `payload` | `RawMessageDeleteEvent` with `cached_message`. |
| `on_raw_bulk_message_delete` | `payload` | `RawBulkMessageDeleteEvent` with `cached_messages`. |
| `on_typing` | `channel, user, when` | `when` is a `datetime`. |
| `on_raw_typing` | `payload` | `RawTypingEvent`. |
| `on_reaction_add` | `reaction, user` | |
| `on_reaction_remove` | `reaction, user` | |
| `on_reaction_clear` | `message, reactions` | `reactions` is the list removed. |
| `on_reaction_clear_emoji` | `reaction` | |
| `on_raw_reaction_add` | `payload` | |
| `on_raw_reaction_remove` | `payload` | |
| `on_raw_reaction_clear` | `payload` | |
| `on_raw_reaction_clear_emoji` | `payload` | |

## Voice

| Event | Arguments | Notes |
| --- | --- | --- |
| `on_voice_state_update` | `member, before, after` | `VoiceState` objects. `before.channel_id` is `None` on a join and `after.channel_id` is `None` on a leave. |

Fluxer lets one user hold several voice connections. Each connection has its own
`connection_id` and fires its own `on_voice_state_update`. Voice states in DM and
group calls have no guild and fire no event; use `on_voice_state_update_data`
for them.

## Commands

| Event | Arguments | Notes |
| --- | --- | --- |
| `on_command` | `ctx` | A command was found and is about to run. |
| `on_command_completion` | `ctx` | The command finished without an error. |
| `on_command_error` | `ctx, error` | See below. |

Command errors go through three levels of handlers, in this order, as in
discord.py:

1. The command's own handler, registered with `@<command>.error`.
2. The cog's `cog_command_error`, when the command is in a cog that overrides it.
3. `on_command_error`, which always runs last as the catch-all.

```py
@bot.command()
async def divide(ctx, a: int, b: int):
    await ctx.send(str(a / b))

@divide.error
async def divide_error(ctx, error):
    if isinstance(error, commands.CommandInvokeError):
        await ctx.send("Can't divide by zero.")

@bot.event
async def on_command_error(ctx, error):
    if ctx.command and ctx.command.has_error_handler():
        return  # already handled locally
    await ctx.send(f"Something went wrong: {error}")
```

Inside a cog, the handler is a method and receives `self` first:
`async def divide_error(self, ctx, error)`. Errors from a command's body arrive
wrapped in `CommandInvokeError`, with the original exception in
`error.original`. Errors such as `BadArgument`, `MissingRequiredArgument` and
`CheckFailure` arrive as they are.

The bot logs an error only when nothing else handles it: no `on_command_error`
listener, no local handler and no cog handler. Overriding
`Bot.on_command_error` in a subclass replaces that default.

## Debug events

These need `enable_debug_events=True` on the client or bot.

| Event | Arguments | Notes |
| --- | --- | --- |
| `on_socket_event_type` | `event_type` | The dispatch name, such as `"MESSAGE_CREATE"`. |
| `on_socket_raw_receive` | `msg` | Each received gateway frame as a string. |
| `on_socket_raw_send` | `payload` | Each sent gateway frame as a string. |

## Fluxer events and raw payloads

Every gateway dispatch is also delivered as `on_<name>_data(payload)` with the
unmodified payload, for example `on_message_reaction_add_data`. Use these when
you need a field the models do not cover.

Dispatches that have no discord.py equivalent keep their Fluxer names and pass
the payload dict, for example `on_relationship_add`, `on_saved_message_create`,
`on_call_create`, `on_guild_members_chunk` and `on_guild_ban_add`. Most of them
also go to `on_fluxer_event(event)` with a typed `RawFluxerEvent`.

These fluxer.py events from before the discord.py names were added keep firing
alongside them: `on_channel_create`, `on_channel_update`, `on_channel_delete`,
`on_channel_pins_update`, `on_guild_member_update`, `on_message_delete_bulk` and
`on_typing_start`.

## discord.py events with no Fluxer equivalent

Fluxer has no feature behind these, so they never fire: application commands and
interactions, AutoMod, scheduled events, stage instances, soundboard sounds,
polls, entitlements and subscriptions, integrations, and voice channel effects.

The shard events `on_shard_connect`, `on_shard_disconnect`, `on_shard_ready` and
`on_shard_resumed` also never fire, because fluxer.py does not run several
shards from one client.
