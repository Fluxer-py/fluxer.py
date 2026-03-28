"""
This is a basic bot example that you can copy-paste for quick usage, it's recommended to copy the whole `bot_subclassed` folder.

This example is somewhat based on https://github.com/PerpetualPossum/fluxer-py-template, check that out!

Feel free to delete this docstring once you copy the code :)

Happy coding!
"""

from .bot import MyBot
import os

bot = MyBot(command_prefix=os.getenv("PREFIX", "!"))

# Run the bot, the MyBot class automatically loads the cogs in the setup_hook method, so we don't need to do anything else here
if __name__ == "__main__":
    # For security reasons, you SHOULDN'T just write your token here directly, but you can (and for example purposes we will just do that).
    # !! Consider using environment variables. !!
    bot.run("token")
