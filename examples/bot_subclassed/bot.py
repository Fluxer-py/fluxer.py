import os

import fluxer
import logging

logger = logging.getLogger(__name__)


class MyBot(fluxer.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Since we are subclassing, we can define bot attributes here instead of having to pass them to the constructor, it's not the best idea to do it this way all the time but it's possible, and you can also modify these attributes at runtime if you want to
        # (Intents are not needed at the moment, this is just an example of how they would be used once required)
        self.intents = fluxer.Intents.default()
        # Set up logging
        logging.basicConfig(level=self.get_log_level())

        # Though it doesn't look nice, you can define commands and events in the constructor like this, but it's generally recommended to use cogs for better organization and separation of concerns, this is just an example to show that it's possible
        # We are working on a better way to implement these directly in the bot subclass, but for now this is how you would do it without cogs
        @self.command(name="ping")
        async def ping(ctx: fluxer.Message):
            """Replies with Pong!"""
            logger.info(f"Received ping command from {ctx.author.display_name}")
            await ctx.reply("Pong!")

        @self.event
        async def on_ready():
            if self.user is not None:
                logger.info(f"Logged in as {self.user}")
            else:
                logger.error("Logged in, but bot user is None. Exiting.")

    # This is called just ONCE before starting the bot, this is a good place to do any setup that needs to be done before the bot actually starts, like loading cogs!
    async def setup_hook(self) -> None:
        # Call our custom method to load cogs
        await self.load_extensions()

    # Custom method to load all python files within the cogs directory as extensions.
    async def load_extensions(self):
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")

    def get_log_level(self) -> int:
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        return getattr(logging, log_level, logging.INFO)
