---
icon: lucide/database-zap
---

# Caching and live state

Each `Client`, including `Bot`, owns one `ConnectionState`. Gateway events update
that state before event callbacks run. Guilds own ID-indexed members, roles,
channels, emojis, and stickers. Client lookups and guild lookups return the same
live objects; updates preserve their identity.

```py
guild = bot.get_guild(guild_id)
if guild is not None:
    member = guild.get_member(user_id)
    role = guild.get_role(role_id)
    channel = guild.get_channel(channel_id)
    assert channel is bot.get_channel(channel_id)
```

## Retention

```py
bot = fluxer.Bot(
    command_prefix="!",
    max_messages=1000,
    cache_members=True,
    max_private_channels=128,
)
```

- `max_messages` bounds messages in insertion/update order. Zero or a negative
  value disables message retention. Lookups do not refresh message recency.
- `cache_members=False` disables retention in guild member collections and
  member lookups. Received messages, voice connections, and event arguments can
  still contain member objects for their own context.
- When omitted, `max_private_channels` defaults to 128 for bot accounts and
  unlimited retention for user accounts. An explicit nonnegative integer applies
  to either account type; zero disables retention and `None` removes the bound.
  Private-channel retrieval and updates refresh LRU recency. Guild channels
  remain cached while visible.
- Users share a weak identity map. A user remains available while a member,
  message, channel recipient, or application reference owns it. The current
  account is retained until state is cleared. ID-only payloads do not erase
  previously hydrated user details.

Eviction affects lookups, not objects an application already holds. Channel
visibility loss removes its cached messages and voice indexes. Guild removal
removes its dependent entries. An unavailable guild stays cached for recovery.
A fresh READY and final shutdown clear state; Resume retains replayable state.

## Members as authors

In a guild, `message.author`, `ctx.author`, and the user passed to
`on_reaction_add` are the author's `GuildMember` whenever one is known: from the
event payload first, otherwise from the member cache. DMs, webhook messages, and
cache misses give a `User`. A `GuildMember` works wherever a `User` does. Account
attributes such as `username`, `bot`, and `avatar_url`, plus `send()`, delegate
to `member.user`, and a member compares and hashes equal to the `User` with the
same ID.

Check the type before using member-only data, or use `ctx.fetch_author()`, which
returns the cached member or fetches it over HTTP:

```py
@bot.command()
async def roles(ctx):
    author = await ctx.fetch_author()
    if isinstance(author, fluxer.GuildMember):
        await ctx.send(f"You have {len(author.roles)} roles")
```

Messages from the gateway share the live cached member. Messages returned by
HTTP calls carry an independent copy of it, like every other HTTP snapshot.

## Guild collections and membership completeness

`guild.members`, `roles`, `channels`, `emojis`, and `stickers` are read-only
sequence views. Iteration, indexing, slicing, and `len()` work. Use ID getters for
constant-time retrieval. Use `list(guild.members)` when an independently mutable
list is needed; its elements still reference the live objects.

The initial member collection is intentionally incomplete. Fluxer supplies the
members needed immediately, not the entire roster. Missing entries therefore do
not establish that a user is outside the guild.

`guild.member_cache_complete` becomes true only when a tracked, explicit,
unfiltered member request has received every chunk and its unique member count
matches the guild total. Filtered requests, disabled retention, interrupted
requests, and capped results that fall short of that total remain incomplete.
The library does not request rosters automatically.

```py
# Sends a request; it does not wait for the full result.
await bot.request_guild_members(guild.id)
# Observe on_guild_members_chunk or its data event for progress, then inspect
# guild.member_cache_complete. A bot's full-roster request is rate limited
# by Fluxer to one accepted request per guild per 30 seconds.
```

Requests use a correlation nonce, generated when none is supplied. Incomplete
tracking expires after 60 seconds; completion and cancellation also release it.
A membership change during an outstanding request invalidates that request's
completeness proof. Request/range state is cleared on a connection interruption,
because member chunks and lazy member-list responses are not replayed.

Lazy member lists keep only the requested ranges. Their `SYNC` operations do not
establish a complete roster, and disappearance from a window does not remove a
guild member. Unknown operations and invalid ranges are ignored.

`channel.permissions_for(user)` raises `RuntimeError` when the user is missing
and the roster is incomplete. Pass an available `GuildMember` directly when
calculating that member's permissions. A complete roster can establish
nonmembership and return an empty permission mask. No permission lookup fetches
data automatically.

## HTTP snapshots

Fetches, message history, search, and model operations parse independent HTTP
snapshots. They retain transport and relationship context, but do not replace
live Gateway cache entries. A late HTTP response cannot overwrite a newer
Gateway event. Snapshot payload collections are independent of live models;
related guild/channel lookups may intentionally resolve live state.

`GuildMember.edit()` also returns an independent snapshot. Read the returned
member for the HTTP result; the receiving live member and its shared user remain
owned by Gateway state.

```py
live = bot.get_channel(channel_id)
snapshot = await bot.fetch_channel(str(channel_id))
assert snapshot is not live
```

Documented local mutations remain local: for example, successful
`channel.set_permissions()` updates the receiving channel's overwrites.
It does not introduce general HTTP cache write-through.
The existing targeted helpers for member roles/timeouts and message pinning also
update their receiving object's corresponding fields after a successful request.

## Event and command execution

The Gateway applies cache mutations in order. Registered state parsers handle
full snapshots, changed subsets, and replacement collections according to each
event's contract. Voice entries use guild, user, and connection identity;
version checks prevent older updates from reviving departed connections.

Event callbacks and commands share one parsed incoming message, even with
message retention disabled. Commands run as tracked background tasks, so a
command awaiting user input or HTTP does not block later cache updates. Commands
can overlap; use command concurrency controls or an application `asyncio.Lock`
where serialization is required. Shutdown cancels outstanding command tasks.

Existing modeled, raw, fallback, and `wait_for` callbacks retain their names and
arguments. `on_<gateway_event_name>_data` still receives the original decoded
payload once. Unknown events remain available through fallback/data events;
there is no retained event-history cache.

## Migration

- Replace assignments or mutations of guild collection lists with API operations.
  Use a local `list(...)` for application-owned sorting or filtering.
- Use returned HTTP snapshots directly instead of assuming `fetch_*()` refreshed
  `get_*()`. Live cache changes come from Gateway events.
- Use the result of `member.edit()` instead of expecting it to replace the
  receiving member's fields.
- Handle incomplete-member errors in user-based permission calculations, or pass
  the member object available on an event/message.
- Review commands that depended on globally serial execution. Shared application
  state may need explicit synchronization.
- Capture values needed for historical records: retained live objects change in
  place as later Gateway events arrive.

For offline measurements and their limitations, see [Cache benchmarks](cache-benchmarks.md).
