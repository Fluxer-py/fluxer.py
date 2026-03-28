from typing import Any, Dict

import fluxer
from fluxer import Cog
import logging

logger = logging.getLogger(__name__)


class OtherCog(Cog):
    def __init__(self, bot: fluxer.Bot):
        super().__init__(bot)

    # Another example listener
    @Cog.listener(name="on_member_join")
    async def on_member_join_example(self, member_dict: Dict[str, Any]):
        # Fluxer.py currently passes the member object as a dict in this event, so we have to manually create a GuildMember object from it
        member: fluxer.GuildMember = fluxer.GuildMember.from_data(member_dict)
        if member.user.bot:
            return
        logger.info(
            f"{member.display_name} has joined the community with ID {member.guild_id}."
        )


async def setup(bot: fluxer.Bot):
    await bot.add_cog(OtherCog(bot))
