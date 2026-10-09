"""Example cog that listens for members joining a community."""

from typing import Any, Dict

from bot import MyBot
import fluxer
from fluxer import Cog
import logging

logger = logging.getLogger(__name__)


class OtherCog(Cog):
    """Cog showing a listener for a non-message event."""

    # Change the bot parameter type to MyBot for better type hinting
    def __init__(self, bot: MyBot):
        """Create the cog for ``bot``."""
        super().__init__(bot)

    # Another example listener
    @Cog.listener(name="on_member_join")
    async def on_member_join_example(self, member_dict: Dict[str, Any]):
        """Log every non-bot member that joins."""
        # Fluxer.py currently passes the member object as a dict in this event, so we have to manually create a GuildMember object from it
        member: fluxer.GuildMember = fluxer.GuildMember.from_data(member_dict)
        if member.user.bot:
            return
        logger.info(
            f"{member.display_name} has joined the community with ID {member.guild_id}."
        )


async def setup(bot: MyBot):
    """Register the cog when the extension is loaded."""
    await bot.add_cog(OtherCog(bot))
