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
