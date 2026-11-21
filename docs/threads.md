---
icon: lucide/messages-square
---

# Threads

A Fluxer thread is a channel, so fluxer.py models threads with the same
`Channel` class as every other channel. `fluxer.channel.Thread` is an alias of
`Channel` for code coming from discord.py. Use `channel.is_thread` to tell a
thread apart, and `thread.parent` to get the channel it lives in.

Thread events (`on_thread_create`, `on_thread_update`, ...) are listed on the
[Events](events.md#channels-and-threads) page.

## Starting a thread

Start a thread from a message, or start one on its own in a text or
announcement channel:

```py
# From a message: always a public thread whose ID is the message's ID
thread = await message.create_thread(name="Discussion")

# Without a message: private by default, as in discord.py
thread = await channel.create_thread(name="Staff only")
thread = await channel.create_thread(
    name="Open chat",
    type=fluxer.ChannelType.PUBLIC_THREAD,
    auto_archive_duration=1440,
)
```

`auto_archive_duration` is the number of minutes without activity before the
thread archives: `60`, `1440`, `4320` or `10080`. When you leave it out Fluxer
uses `4320` (3 days). Fluxer does not apply the channel's
`default_auto_archive_duration` to new threads, so fluxer.py doesn't send it
either, unlike discord.py.

`message.thread` returns the thread started from a message, and
`message.fetch_thread()` fetches it.

## Editing, archiving and deleting

`Channel.edit()` sends only the fields you pass:

```py
await thread.edit(name="Resolved", archived=True, locked=True)
await thread.edit(slowmode_delay=10)
await thread.delete(reason="Spam")
```

The thread's owner and thread moderators can rename, archive, lock and change
`auto_archive_duration` or `invitable`. Any member can unarchive a thread, and
sending a message in an archived thread unarchives it too. Changing the
slowmode and unlocking need a thread moderator: the guild owner, an
administrator, or a member with `MANAGE_THREADS` on the parent channel.

The same `edit()` works on regular channels, for example
`await channel.edit(topic="Rules", default_thread_slowmode_delay=30)`.

## Members

```py
await thread.join()
await thread.leave()
await thread.add_user(member)
await thread.remove_user(member)

members = await thread.fetch_members()     # every ThreadMember
member = await thread.fetch_member(user_id)
```

`thread.me` is the bot's own `ThreadMember`, and `thread.thread_members` holds
the members seen joining since the thread was cached.

## Finding threads

Active threads are cached:

```py
guild.threads                 # every cached thread in the guild
guild.get_thread(thread_id)
channel.threads               # cached threads of one channel
channel.get_thread(thread_id)
```

Archived threads leave the cache. Fetch them page by page with
`archived_threads()`, newest first:

```py
async for thread in channel.archived_threads(limit=50):
    print(thread.name)

# Private archived threads need a thread moderator
async for thread in channel.archived_threads(private=True):
    ...

# Only the private threads the bot is in
async for thread in channel.archived_threads(private=True, joined=True):
    ...
```

`await guild.active_threads()` fetches every active thread in the guild without
adding them to the cache.

## Thread permissions

Threads have no permission overwrites of their own. `thread.permissions_for()`
returns the parent channel's permissions, and sending in a thread needs
`SEND_MESSAGES_IN_THREADS` instead of `SEND_MESSAGES`. The thread permissions
are `MANAGE_THREADS`, `CREATE_PUBLIC_THREADS`, `CREATE_PRIVATE_THREADS` and
`SEND_MESSAGES_IN_THREADS`.

## Commands

`commands.ThreadConverter` turns an ID, a `<#id>` mention or a name into a
cached thread, and raises `ThreadNotFound` otherwise. Since `Thread` is the same
class as `Channel`, a `fluxer.Channel` annotation still uses the channel
converter, so ask for the thread converter explicitly:

```py
@bot.command()
async def close(ctx, thread: commands.ThreadConverter):
    await thread.edit(archived=True, locked=True)
```

## Things to know

- `fetch_members()`, `fetch_member()` and `guild.active_threads()` are bot-only.
  Fluxer returns 404 to user accounts.
- User accounts must declare Fluxer's `channel_threads` capability to use thread
  routes. fluxer.py sends it on every thread request; bots don't need it.
- Forum and media channels (posts and tags) and announcement publishing and
  following are not supported yet.
