__version__ = "0.4.1"
__title__ = "fluxer.py"
__author__ = "Emil"
__license__ = "MIT"

# Core classes
from .client import Bot, Client, when_mentioned_or, when_mentioned
from .cog import Cog
from .enums import ChannelType, GatewayCloseCode, GatewayOpcode, Intents, Permissions
from .file import File
from .http import HTTPClient

# Checks
from .checks import has_role, has_permission

# Errors
from .errors import (
    BadRequest,
    FluxerException,
    Forbidden,
    GatewayException,
    GatewayNotConnected,
    HTTPException,
    LoginFailure,
    NotFound,
    RateLimited,
    Unauthorized,
)

# Models
from .models import (
    Channel,
    Embed,
    Emoji,
    Guild,
    GuildMember,
    Message,
    Reaction,
    Role,
    User,
    UserProfile,
    VoiceState,
    Webhook,
)

# Voice support is optional so only import if available
try:
    from .voice import FFmpegPCMAudio, VoiceClient
except ImportError:
    pass

# Utilities
from .utils import datetime_to_snowflake, snowflake_to_datetime

__all__ = [
    # Checks
    "has_role",
    "has_permission",
    # Client
    "Bot",
    "Client",
    "when_mentioned",
    "when_mentioned_or",
    "Cog",
    "File",
    "HTTPClient",
    # Enums
    "ChannelType",
    "GatewayCloseCode",
    "GatewayOpcode",
    "Intents",
    "Permissions",
    # Errors
    "BadRequest",
    "FluxerException",
    "Forbidden",
    "GatewayException",
    "GatewayNotConnected",
    "HTTPException",
    "LoginFailure",
    "NotFound",
    "RateLimited",
    "Unauthorized",
    # Models
    "Channel",
    "Embed",
    "Emoji",
    "Guild",
    "GuildMember",
    "Message",
    "Reaction",
    "Role",
    "User",
    "UserProfile",
    "VoiceState",
    "Webhook",
    # Utils
    "datetime_to_snowflake",
    "snowflake_to_datetime",
    # Voice (present only when the 'voice' extra is installed)
    "FFmpegPCMAudio",
    "VoiceClient",
]
