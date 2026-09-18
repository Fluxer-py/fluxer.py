from bot import MyBot
import fluxer
from fluxer import Cog
from fluxer.checks import has_permission
from fluxer.ext.commands import Context
import logging

logger = logging.getLogger(__name__)


class CogExample(Cog):
    # Change the bot parameter type to MyBot for better type hinting
    def __init__(self, bot: MyBot):
        super().__init__(bot)

    # Example Listener
    @Cog.listener(
        name="on_message"  # <- You can change the event name to listen to other events, see other_cog_example for a different event example
    )
    # Cog events need the self arg!
    async def on_message_example(self, message: fluxer.Message):
        if message.author.bot:
            return
        guild_name: str | None = None
        if message.guild is not None:
            guild_name = message.guild.name
        logger.info(
            f"Received message from {message.author.display_name} in {guild_name}: {message.content}"
        )

    # Mark this method as a cog command
    @Cog.command()
    # Automatically check if the member has a community permission, otherwise they can't execute the command
    @has_permission(fluxer.Permissions.KICK_MEMBERS)
    # Cog commands need the self arg!
    async def kick(self, ctx: Context, user_id: int):
        logger.info(f"Received kick command from {ctx.author.display_name}")

        if ctx.message.guild_id is None:
            await ctx.reply("This command can only be used in a server.")
            return
        guild = await ctx.bot.fetch_guild(str(ctx.message.guild_id))

        try:
            await guild.kick(int(user_id))
            await ctx.reply(f"User with ID {user_id} has been kicked.")
            logger.info(f"Kicked user with ID {user_id}")
        except Exception as e:
            await ctx.reply(
                "Failed to kick user, please check with the bot owner for more details."
            )
            logger.error(f"Failed to kick user with ID {user_id}. Error: {e}")


# Method called to actually register the Cog class
async def setup(bot: MyBot):
    await bot.add_cog(CogExample(bot))
