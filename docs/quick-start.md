---
icon: lucide/bot
---

# Quick Start

!!! danger
    This documentation is a _Work in Progress_ and only meant to be used with the current [rework version](https://github.com/Fluxer-py/fluxer.py/tree/rework) of Fluxer.py, if you are not sure you're using it, you're probably using the stable 0.4.2 version and this docs might not work for  you.

A simple bot with a ping command:

```py
import os

import fluxer
from fluxer.ext import commands

bot = fluxer.Bot(command_prefix="!")

@bot.event
async def on_ready():
    print(f"Bot is ready! Logged in as {bot.user}")

@bot.command()
async def ping(ctx: commands.Context):
    await ctx.reply("Pong!")

if __name__ == "__main__":
    TOKEN = "your_bot_token"
    bot.run(TOKEN)
```

`fluxer.Bot` is the command bot exported from `fluxer.ext.commands`. Its help
command is available as soon as you create the bot with a prefix. Users can run
`!help` to list commands and `!help ping` for details about `ping`.

Commands with aliases and groups are included too:

```py
@bot.command(aliases=["hi"])
async def greet(ctx: commands.Context):
    """Greet the caller."""
    await ctx.reply("Hello!")

@bot.group()
async def tools(ctx: commands.Context):
    """Utility commands."""

@tools.command(aliases=["ls"])
async def list_items(ctx: commands.Context):
    """List available items."""
```

Use `!help greet` or `!help hi` for the aliased command, `!help tools` for the
group, and `!help tools list_items` or `!help tools ls` for its subcommand.
Pass `help_command=None` when constructing the bot to disable built-in help,
or provide a `commands.HelpCommand` instance to replace it. A command prefix
is required when constructing `fluxer.Bot`.
