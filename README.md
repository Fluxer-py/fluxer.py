# fluxer.py

A Python API wrapper for [Fluxer](https://fluxer.app).

Build bots and automated clients with a clean, type-safe, and
event-driven architecture.

------------------------------------------------------------------------

## Features

-   Async-first design built on `asyncio`
-   REST API support with automatic rate limiting
-   WebSocket gateway for real-time events
-   Command framework with decorators
-   Modular cog system
-   Strongly-typed data models
-   Structured error handling and retry logic
-   Clean separation between low-level `Client` and high-level `Bot`

------------------------------------------------------------------------

## Installation

``` sh
pip install fluxer.py
```

Requires Python 3.10 or higher.

### Voice support

Voice requires `LiveKit` and `ffmpeg`:

``` sh
pip install fluxer.py[voice]
```

or

```sh
uv add fluxer.py --extra voice
```

ffmpeg must be installed separately and available on your `PATH`.

On macOS (assuming you have [Brew](https://brew.sh/)):

``` sh
brew install ffmpeg
```

On Debian/Ubuntu:

``` sh
apt install ffmpeg
```

On Windows: (assuming you have [Chocolatey](https://chocolatey.org/install))
```sh
choco install ffmpeg
```

For development:

``` sh
git clone https://github.com/akarealemil/fluxer.py.git
cd fluxer.py
pip install -e .
```

------------------------------------------------------------------------

## Quick Start

A simple bot with a ping command:

``` py
import fluxer

bot = fluxer.Bot(command_prefix="!", intents=fluxer.Intents.default())

@bot.event
async def on_ready():
    print(f"Bot is ready! Logged in as {bot.user.username}")

@bot.command()
async def ping(ctx):
    await ctx.reply("Pong!")

if __name__ == "__main__":
    TOKEN = "your_bot_token"
    bot.run(TOKEN)
```

------------------------------------------------------------------------

## Choosing Between Bot and Client

### Bot

Use `Bot` if you need: - Decorator-based commands - Built-in command
parsing - Cog support - Rapid bot development

### Client

Use `Client` if you need: - Full event-driven control - A custom command
framework - Lower-level API interaction - Advanced or specialized
implementations

------------------------------------------------------------------------

## Architecture Overview

`Bot` extends `Client`, adding a command framework on top of the core
event system.

Core components:

-   `HTTPClient` -- Handles REST requests and rate limits
-   `Gateway` -- Manages WebSocket connection and event dispatch
-   `Client` -- Base event-driven interface
-   `Bot` -- High-level command framework
-   `Cog` -- Modular command grouping system

------------------------------------------------------------------------

## Data Models

`fluxer.py` provides strongly-typed models representing Fluxer entities:

-   `Guild`
-   `Channel`
-   `Message`
-   `User`
-   `GuildMember`
-   `VoiceState`
-   `Webhook`
-   `Embed`
-   `Emoji`

Models encapsulate both state and behavior, exposing convenience methods
such as:

-   `Message.reply()`
-   `Channel.send()`
-   `Guild.kick_member()`

------------------------------------------------------------------------

## Voice

Requires `fluxer.py[voice]` and ffmpeg

``` py
@bot.command()
async def play(ctx, channel_id: int, *, path: str):
    channel = await bot.fetch_channel(str(channel_id))

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

`FFmpegPCMAudio` accepts the same options as discord.py's `FFmpegPCMAudio`:

| Parameter | Description |
|---|---|
| `executable` | Path to ffmpeg binary (default: `"ffmpeg"`) |
| `before_options` | Arguments inserted before `-i` (e.g. `"-ss 30"` to seek) |
| `options` | Arguments inserted after the source (e.g. `"-filter:a volume=0.5"`) |
| `sample_rate` | Output sample rate in Hz (default: `48000`) |
| `num_channels` | `1` for mono, `2` for stereo (default: `2`) |

------------------------------------------------------------------------

## Intents

`Intents` determine which events your application receives from the
WebSocket gateway.

Common usage:

``` py
fluxer.Intents.default()
fluxer.Intents.all()
```

Limiting intents improves performance and ensures your application
subscribes only to necessary events.

------------------------------------------------------------------------

## Exceptions

All library exceptions inherit from:

``` py
FluxerException
```

Errors include:

-   HTTP errors mapped to REST status codes
-   Gateway protocol errors
-   Connection and retry-related failures

------------------------------------------------------------------------

## Documentation

Full documentation is available at:

https://deepwiki.com/akarealemil/fluxer.py/1-overview

------------------------------------------------------------------------

## Contributing

We use `uv` for dependency management.

``` sh
git clone https://github.com/akarealemil/fluxer.py.git
cd fluxer.py
uv sync --dev
```

This will create a `.venv` and install development dependencies.
