"""Example: Working with user display names and nicknames."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import load_dev_token

from fluxer.http import HTTPClient
from fluxer.models.user import User


async def main():
    token = load_dev_token()
    user_id = sys.argv[1] if len(sys.argv) > 1 else None

    async with HTTPClient(token) as http:
        data = (
            await http.get_user(user_id) if user_id else await http.get_current_user()
        )
        user = User.from_data(data, http)

        print("=" * 60)
        print("User Information")
        print("=" * 60)
        print(f"ID:            {user.id}")
        print(f"Username:      {user.username}")
        print(f"Discriminator: {user.discriminator}")
        print(f"Global Name:   {user.global_name or '(not set)'}")
        print(f"Display Name:  {user.display_name}")
        print(f"Bot:           {user.bot}")
        print(f"Avatar URL:    {user.avatar_url or user.default_avatar_url}")
        print(f"Created At:    {user.created_at}")


if __name__ == "__main__":
    asyncio.run(main())
