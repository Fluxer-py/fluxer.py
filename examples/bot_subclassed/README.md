# _Subclassed Bot_ Example

> [!IMPORTANT]
> This is partialy based on [Fluxer.py Template](https://github.com/PerpetualPossum/fluxer-py-template), if you want a quick, easily clonable, ready-to-go setup, check that out!

## Features

- Bot subclassing
- Bot class listeners
- Bot class commands
- Permission checking with commands
- Hooking into your bot's setup
- Cog (extensions) usage
- Cog commands (commands within Cog classes)
- Cog listeners (listeners within Cog classes)

## Setup

### Requirements

- Python 3.10 or higher
- A computer

> [!NOTE]
> Though Python 3.10 is supported, version 3.14 is currently (27/03/2026) recommended for it's [current status](https://devguide.python.org/versions/).

### Usage steps

For this example, follow these steps:

1. Copy the `bot_subclassed` folder somewhere in your computer
2. Get inside your `bot_subclassed` directory
3. Open a terminal (Command Prompt, Powershell, Bash, whatever) within your `bot_subclassed` directory
4. Run `python3 -m venv .venv` to create a [Virtual Environment (venv)](https://docs.python.org/3/library/venv.html)
5. [Activate](https://docs.python.org/3/library/venv.html#how-venvs-work) your venv
    - Windows:
      - For **Command Prompt** Execute `.\.venv\Scripts\activate.bat`
      - For **Powershell** Execute `.\.venv\Scripts\Activate.ps1` (if it doesn't work just use Command Prompt or read [the python documentation](https://docs.python.org/3/library/venv.html#how-venvs-work))
    - Bash: Execute `./.venv/bin/activate`
6. While your venv is active:
   1. Run `pip install -r requirements.txt` to install the required dependencies for this example
   2. Run `python3 main.py`
   3. Enjoy your bot :D