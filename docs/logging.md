---
icon: lucide/scroll-text
---

# Logging

fluxer.py logs through Python's standard `logging` module, under the `fluxer`
logger (`fluxer.client`, `fluxer.gateway`, `fluxer.http`, ...). `bot.run()` sets
up a console handler for you, the same way discord.py does, so a new bot prints
its connection and rate limit messages without any setup:

```py
bot = fluxer.Bot(command_prefix="!")
bot.run(TOKEN)
```

```text
2026-10-18 13:30:02 INFO     fluxer.client Logging in using static token
2026-10-18 13:30:03 INFO     fluxer.gateway Connected to gateway as my-bot (session ID: ...)
```

Output is coloured when the terminal supports it. Set the `NO_COLOR`
environment variable to turn colour off.

## Prettier output with rich

Install the `rich` extra and the console handler switches to
[rich](https://github.com/Textualize/rich) automatically, with aligned columns
and readable tracebacks:

```sh
pip install "fluxer.py[rich]"
```

rich is only used when output goes to a terminal. When output is redirected to
a file or a log collector, plain text is written instead. Pass `use_rich=False`
to never use it, or `use_rich=True` to always use it.

## Configuring `run()`

`run()` takes the same logging arguments as discord.py's:

```py
import logging

bot.run(
    TOKEN,
    log_level=logging.DEBUG,       # or "DEBUG"; defaults to INFO
    root_logger=True,              # also print your own loggers
    log_handler=logging.FileHandler("bot.log", encoding="utf-8"),
    log_formatter=logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"),
)
```

- `log_handler`: where logs go. Defaults to the console.
- `log_formatter`: how lines look. Defaults to the coloured format, or rich's.
- `log_level`: the level for fluxer.py's logs, as a number or a name.
- `root_logger`: set it to `True` so that loggers in your own code, such as
  `logging.getLogger(__name__)` in a cog, print through the same handler.
- `use_rich`: `None` (automatic), `True` or `False`, as above.

Pass `log_handler=None` to leave logging completely alone.

If your code already configures logging before calling `run()`, for example
with `logging.basicConfig()` or `logging.config.dictConfig()`, `run()` keeps your
setup and adds nothing, so lines are never printed twice. A `log_level` you pass
is still applied to the `fluxer` logger. `start()` never touches logging.

## Without `run()`

When you call `await bot.start(TOKEN)` yourself, set up logging first with
`fluxer.utils.setup_logging()`. It takes the same options:

```py
import fluxer

fluxer.utils.setup_logging(level="INFO")  # root logger by default
await bot.start(TOKEN)
```

Unlike `run()`, `setup_logging()` configures the root logger by default, so your
own loggers print too; pass `root=False` to only configure `fluxer`. Calling it
again replaces the handler it added before instead of adding another one.

## What is logged

| Level | Examples |
| --- | --- |
| `DEBUG` | Every REST response status, rate limit bucket changes, gateway payloads (opcode and event name only), heartbeats, dispatched events |
| `INFO` | Logging in, gateway connected, reconnects and resumes |
| `WARNING` | Rate limits and retries, server errors that are retried, network failures, high gateway latency |
| `ERROR` | Errors in your event handlers and commands (unless you handle them), fatal gateway close codes |

Requests are logged by route, such as `POST /channels/{channel_id}/messages:channel_id=123`.
Full URLs, request and response bodies, and tokens are never logged, so webhook
tokens stay out of your log files even at `DEBUG`.
