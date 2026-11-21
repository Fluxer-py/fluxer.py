---
icon: lucide/square-library
---

# Architecture Overview

!!! danger
    This documentation is a _Work in Progress_ and only meant to be used with the current [rework version](https://github.com/Fluxer-py/fluxer.py/tree/rework) of Fluxer.py, if you are not sure you're using it, you're probably using the stable 0.4.2 version and this docs might not work for  you.

`fluxer.ext.commands.Bot` extends `Client`, adding a command framework on
top of the core event system.

Core components:

- `HTTPClient` -- Handles REST requests and rate limits
- `Gateway` -- Manages WebSocket connection, heartbeat, resume, and documented gateway sends
- `Client` -- Base event interface, cache owner, waiters, and REST/model helper surface
- `fluxer.ext.commands` -- Commands, groups, cogs, checks, converters, cooldowns, and help commands
- `fluxer.ext.tasks` -- Reusable background task loops
- `VoiceClient` -- Optional voice connection and playback support

See [Caching and live state](caching.md) for retention settings, read-only guild
collections, incomplete membership, HTTP snapshots, and command execution.

---

# Data Models

`fluxer.py` provides strongly-typed models representing Fluxer entities:

-   `Guild`
-   `Channel`
-   `Message`
-   `User`
-   `GuildMember`
-   `VoiceState`
-   `Webhook`
-   `WebhookMessage`
-   `Embed`
-   `Emoji`
-   `Reaction`
-   `Role`
-   `MessageReference`
-   `PartialMessage`
-   `AllowedMentions`
-   `Object`
-   `Colour` / `Color`

Models encapsulate both state and behavior, exposing convenience methods
such as:

- `Message.reply()`
- `Message.edit()`
- `Message.add_reaction()`
- `Channel.send()`
- `Channel.history()`
- `Channel.get_partial_message()`
- `Guild.fetch_member()`
- `Guild.ban()`
- `Webhook.send()`

For guild members, `member.display_name` chooses the guild nickname when one
is set, then the account's global name or username. `member.display_avatar`
chooses the guild avatar, then the account avatar, then its generated default
avatar. The avatar property returns a URL using the member's initialized
client service endpoints.

Messages and webhook messages expose reply or forward metadata through
`message.reference`. When present, it is the same object as
`message.message_reference`; `message.reference.resolved` contains the referenced
`Message`, a `DeletedReferencedMessage` placeholder, or `None` when unresolved.
The existing `message.referenced_message` field remains available. Accessing
`reference` does not fetch a message or change the reference's wire payload.

Forwarded messages expose `message.message_snapshots` as a list of
`MessageSnapshot` objects; webhook messages use the same model. Each snapshot
has the original `timestamp` string and a `created_at` datetime, plus optional
`edited_timestamp` and `edited_at`. `mentions` and `mention_roles` contain
integer IDs. `attachments`, `stickers`, `embeds` (`Embed`), and
`mention_channels` (`ChannelMention`) are parsed models, and `flags` is a
`MessageFlags` mask.
Optional collections are empty when omitted. `raw_data` retains the original
snapshot fields, including fields without typed properties. A snapshot contains
only the fields supplied by Fluxer; it does not resolve a source message.

## Embed timestamps

`Embed.timestamp` is an aware `datetime`. Pass a `datetime` or an ISO8601
string and the library normalises it; naive datetimes are taken as local time,
the same rule `format_dt` uses. Outgoing embeds send the timestamp as a UTC
ISO8601 string, and received embeds parse Fluxer's `...Z` strings into a
datetime, so no manual conversion is needed in either direction:

```py
from fluxer.utils import utcnow

embed = fluxer.Embed(title="Report", timestamp=utcnow())
embed.timestamp = "2026-08-31T09:14:02.000Z"  # also accepted
print(message.embeds[0].timestamp.year)  # datetime on received embeds
```

## Allowed mentions

`AllowedMentions` decides which mentions in a message's text notify anyone. It
works as in discord.py: pass it per message, or set it once on the client and
every message uses it. A per-message object only replaces the fields it sets.

```py
bot = fluxer.Bot(
    command_prefix="!",
    allowed_mentions=fluxer.AllowedMentions(everyone=False),
)

# Only the command author is pinged, and the reply does not ping anyone else.
await ctx.send(
    f"{ctx.author.mention} done!",
    allowed_mentions=fluxer.AllowedMentions(users=[ctx.author]),
)

# Reply without notifying the author of the original message.
await message.reply("pong", mention_author=False)
```

`users` and `roles` take users, members, roles, `fluxer.Object` or plain IDs,
at most 100 each. `send`, `reply`, `edit` and webhook sends all accept
`allowed_mentions`, and `send` and `reply` also accept `mention_author`. On an
edit, the client-wide policy is only applied when the text changes, and
`allowed_mentions=None` clears the stored policy.

Fluxer does not let a message list specific users or roles and also allow whole
categories such as `@everyone`. When `users` or `roles` is a list, every
category you did not set is turned off. Setting one to `True` next to a list,
as in `AllowedMentions(everyone=True, users=[member])`, raises `ValueError`.

## Message and attachment flags

`Message.flags` and `WebhookMessage.flags` expose `MessageFlags`. The boolean
properties `suppress_embeds`, `suppress_notifications`, and `voice_message`
correspond to Fluxer's documented message bits. Attachments expose
`AttachmentFlags` with `is_spoiler`, `contains_explicit_media`, and
`is_animated`. `Attachment.is_spoiler()` checks the spoiler bit directly:

```py
if message.flags.suppress_embeds:
    print("Embeds are hidden")

for attachment in message.attachments:
    if attachment.is_spoiler():
        print("Spoiler attachment:", attachment.filename)
```

Use `int(model.flags)` or `model.flags.value` to read the complete mask,
including bits without named properties. Attachment payload serialization
still writes an integer mask.

## Images and assets

Images served by the Fluxer Media Proxy are exposed as `Asset` objects:
`user.avatar`, `user.banner`, `member.display_avatar`, `member.guild_avatar`,
`guild.icon`, `guild.banner`, `guild.splash`, `emoji.asset`, `sticker.asset`,
and more. A property is `None` when the image is not set. Each also has a
`*_url` string shortcut, such as `user.avatar_url` or `guild.icon_url`. The raw
image hashes stay available as `*_hash` fields, such as `guild.icon_hash`.

```py
avatar = member.display_avatar  # guild avatar, account avatar, or default
print(avatar.url)
thumb = avatar.with_size(256).with_static_format("webp")
data = await thumb.read()
await avatar.save("avatar.png")
await channel.send(file=await avatar.to_file(filename="avatar.png"))
```

- `with_size()` requests an edge length. The Media Proxy rounds it up to its
  next supported step and keeps it within the limits for that kind of image.
- `with_format()` accepts `png`, `jpg`, `jpeg`, `webp`, `gif`, `apng`, and
  `avif`. `with_static_format()` changes only non-animated images.
- Default avatars come from the instance's static CDN and are not transformed,
  so the `with_*` methods return them unchanged.
- Animated avatars, icons, and banners (hashes starting with `a_`) default to
  `gif`. Emojis and stickers use `webp` and request animation when animated.
- Building a URL needs a client bound to an instance (`instance_url`). An
  unbound model raises `RuntimeError` when its URL is read.

Attachments are not rebuilt from a hash. `attachment.read()`, `save()`, and
`to_file()` download the URL Fluxer issued. Pass `use_cached=True` to use
`proxy_url` instead.

---

# Channel permissions

Guild channels expose both effective permissions and individual overwrite
records. These helpers use the guild data already bound to the channel and do
not make hidden requests:

``` py
import fluxer

# Calculate the member's effective mask from cached guild roles and overwrites.
effective = channel.permissions_for(member)
if effective & fluxer.Permissions.SEND_MESSAGES:
    print("The member can send messages here.")

# Inspect an existing overwrite as tri-state permission values.
overwrite = channel.overwrites_for(member)
print(overwrite.send_messages)  # True, False, or None

# Create or replace one member overwrite.
await channel.set_permissions(
    member,
    send_messages=True,
    manage_messages=False,
)

# Bare IDs must state whether they identify a role or member.
await channel.set_permissions(
    role_id,
    type=fluxer.PermissionOverwriteType.ROLE,
    overwrite=fluxer.PermissionOverwrite(view_channel=True),
)

# Delete that single overwrite.
await channel.set_permissions(
    role_id,
    type=fluxer.PermissionOverwriteType.ROLE,
    overwrite=None,
)
```

`channel.permission_overwrites` retains Fluxer's raw decimal-string dictionaries.
Use `channel.overwrites` for immutable typed records.

---

# Voice

Requires `fluxer.py[voice]` and ffmpeg

``` py
import fluxer
from fluxer.ext import commands

bot = commands.Bot(command_prefix="!")

@bot.command()
async def play(ctx: commands.Context, channel_id: int, *, path: str):
    channel = await bot.fetch_channel(channel_id)

    async with await channel.connect(bot) as vc:
        await vc.play_file(path)
```

For background playback with an `after` callback:

``` py
async with await channel.connect(bot) as vc:
    vc.play(fluxer.FFmpegPCMAudio("music.mp3"), after=lambda e: print("done"))
    # bot continues handling commands while audio plays
```

Pause and resume mid-playback:

``` py
vc.pause()
vc.resume()
print(vc.is_paused)  # bool
```

`FFmpegPCMAudio` accepts common ffmpeg source options:

| Parameter | Description |
|---|---|
| `executable` | Path to ffmpeg binary (default: `"ffmpeg"`) |
| `before_options` | Arguments inserted before `-i` (e.g. `"-ss 30"` to seek) |
| `options` | Arguments inserted after the source (e.g. `"-filter:a volume=0.5"`) |
| `sample_rate` | Output sample rate in Hz (default: `48000`) |
| `num_channels` | `1` for mono, `2` for stereo (default: `2`) |

Voice state data is cached from gateway events and can be read with
`Client.get_channel_voice_states()` and
`Client.get_channel_voice_user_count()`.

------------------------------------------------------------------------

# Connections and presence

The client discovers REST, Gateway, media, and link services from the instance's
`/.well-known/fluxer` document. The default origin is `https://fluxer.app`.
Pass `instance_url="https://chat.example.org"` to connect to another instance.
An explicit `api_url` is an already-versioned REST override; by itself it does
not discover ancillary services or guess asset URLs.

`Intents` is retained for compatibility. Fluxer does not use it to filter events,
and explicitly passing a mask emits `DeprecationWarning`. Omit it in new code.
Use a string or `CustomActivity` for custom status; rich activities such as
`Game`, `Streaming`, and `Spotify` cannot be published.

```python
await bot.change_presence(activity="Answering questions")
await bot.change_presence(status="idle")  # Preserve the custom status.
await bot.change_presence(activity=None)  # Clear the custom status.
```

Edits distinguish omission from clearing: `await message.edit(embed=embed)`
preserves text, while `await message.edit(content=None)` clears it. Channel
history and pinned-message helpers return one page, not an unlimited traversal.
History accepts 1?100 messages; pin cursors are ISO8601 pin timestamps.

The transport retains stable error codes, localized messages, and validation
details. It distinguishes JSON, empty responses, and Slack's text response.
Retries of mutations cannot guarantee exactly-once delivery. A global denial of
an existing user session marks it invalid and stops retries with that credential.

```python
import asyncio
import os
from fluxer.http import HTTPClient
from fluxer.errors import HTTPException

async def main():
    async with HTTPClient(os.environ["FLUXER_TOKEN"], max_retries=2) as http:
        try:
            user = await http.get_current_user()
            print(user["username"])
        except HTTPException as error:
            print(error.status, error.code, error.message)

asyncio.run(main())
```

Voice requires `pip install fluxer.py[voice]`, plus FFmpeg for PCM file playback.
Voice clients retain the server-issued connection ID for cleanup; encrypted
grants unsupported by this integration fail explicitly.

# Exceptions

All library exceptions inherit from:

```py
FluxerException
```

Errors include:

- `HTTPException`, `BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, and `RateLimited`
- `GatewayException` and `GatewayNotConnected`
- `LoginFailure` and connection-related failures

---
