"""Test fetching guild member data including nicknames and roles."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import load_dev_token

from fluxer.http import HTTPClient
from fluxer.models.member import GuildMember


async def main():
    token = load_dev_token()

    if len(sys.argv) < 3:
        print("Usage: python tests/member_smoke.py <guild_id> <user_id>")
        sys.exit(1)

    guild_id = sys.argv[1]
    user_id = sys.argv[2]

    async with HTTPClient(token) as http:
        data = await http.get_guild_member(guild_id, user_id)
        member = GuildMember.from_data(data, http)

        print("=" * 60)
        print("Guild Member Information")
        print("=" * 60)
        print(f"User ID:        {member.user.id}")
        print(f"Username:       {member.user.username}#{member.user.discriminator}")
        print(f"Guild Nickname: {member.nick or '(not set)'}")
        print(f"Display Name:   {member.display_name}")
        print(f"Roles:          {len(member.roles)} role(s)")
        print(f"Joined At:      {member.joined_at}")


if __name__ == "__main__":
    asyncio.run(main())
