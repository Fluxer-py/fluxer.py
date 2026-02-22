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

For development:

``` sh
git clone https://github.com/akarealemil/fluxer.py.git
cd fluxer-py
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
-   `Webhook`
-   `Embed`
-   `Emoji`

Models encapsulate both state and behavior, exposing convenience methods
such as:

-   `Message.reply()`
-   `Channel.send()`
-   `Guild.kick_member()`

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
cd fluxer-py
uv sync --dev
```

This will create a `.venv` and install development dependencies.
