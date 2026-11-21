"""This is a basic bot example that you can copy-paste for quick usage, it's recommended to copy the whole `bot_basic` folder.

This example is heavily based on https://github.com/PerpetualPossum/fluxer-py-template, check that out!

Feel free to delete this docstring once you copy the code :)

Happy coding!
"""

import fluxer
import os
import logging
import asyncio
from fluxer.ext.commands import Context


# Set up coloured console logging (rich output when `fluxer.py[rich]` is installed).
# bot.run() does this for you; this example calls bot.start() itself, so it sets it up here.
fluxer.utils.setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

bot = fluxer.Bot(command_prefix=os.getenv("PREFIX", "!"))


# Event listening through the bot object, you can listen to other events like on_message, on_member_join, etc.
@bot.event
async def on_ready() -> None:
    """Log the authenticated account when ready.

    Returns:
        None.
    """
    if bot.user is not None:
        logger.info(f"Logged in as {bot.user}")
    else:
        logger.error("Logged in, but bot user is None. Exiting.")


# You can define commands directly in here, but it's not really tidy this way, consider using cogs
@bot.command()
async def ping(ctx: Context) -> None:
    """Reply with Pong!

    Args:
        ctx: Context for the command invocation.
    """
    logger.info(f"Received ping command from {ctx.author.display_name}")
    await ctx.reply("Pong!")


# Load local extensions before connecting to the Gateway.
async def load_extensions() -> None:
    """Load Python extensions from the local cogs directory.

    Returns:
        None.
    """
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


async def main() -> None:
    """Load extensions and start the bot."""
    await load_extensions()
    # For security reasons, you SHOULDN'T just write your token here directly, but you can (and for example purposes we will just do that).
    # !! Consider using environment variables. !!
    await bot.start("token")


if __name__ == "__main__":
    asyncio.run(main())
