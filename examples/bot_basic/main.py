"""
This is a basic bot example that you can copy-paste for quick usage, it's recommended to copy the whole `bot_basic` folder.


This example is heavily based on https://github.com/PerpetualPossum/fluxer-py-template, check that out!

Feel free to delete this docstring once you copy the code :)

Happy coding!
"""

import fluxer
import os
import logging
import asyncio


def get_log_level() -> int:
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, log_level, logging.INFO)


# Set up logging
logging.basicConfig(level=get_log_level())
logger = logging.getLogger(__name__)

bot = fluxer.Bot(
    command_prefix=os.getenv("PREFIX", "!"), intents=fluxer.Intents.default()
)


# Event listening through the bot object, you can listen to other events like on_message, on_member_join, etc.
@bot.event
async def on_ready():
    if bot.user is not None:
        logger.info(f"Logged in as {bot.user}")
    else:
        logger.error("Logged in, but bot user is None. Exiting.")


# You can define commands directly in here, but it's not really tidy this way, consider using cogs
@bot.command()
async def ping(ctx: fluxer.Message):
    """Replies with Pong!"""
    logger.info(f"Received ping command from {ctx.author.display_name}")
    await ctx.reply("Pong!")


# This will automatically load all your cogs found under the `cogs` directory, it has to be executed before running the bot, otherwise the cogs won't be loaded and their commands/listeners won't work.
async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


# Run the bot, this will also load the cogs before starting the bot
if __name__ == "__main__":
    asyncio.run(load_extensions())
    # For security reasons, you SHOULDN'T just write your token here directly, but you can (and for example purposes we will just do that).
    # !! Consider using environment variables. !!
    bot.run("token")
