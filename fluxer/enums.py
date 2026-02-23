from __future__ import annotations

import enum

# =============================================================================
# Gateway Opcodes
# Fluxer mirrors Discord's opcode structure since it's wire-compatible.
# =============================================================================


class GatewayOpcode(enum.IntEnum):
    """Gateway opcodes define the type of payload being sent/received."""

    DISPATCH = 0  # Server -> Client: An event was dispatched
    HEARTBEAT = 1  # Bidirectional: Maintain connection / request heartbeat
    IDENTIFY = 2  # Client -> Server: Start a new session
    PRESENCE_UPDATE = 3  # Client -> Server: Update client presence/status
    VOICE_STATE_UPDATE = 4  # Client -> Server: Join/move/leave voice channels
    RESUME = 6  # Client -> Server: Resume a dropped connection
    RECONNECT = 7  # Server -> Client: Client should reconnect
    REQUEST_GUILD_MEMBERS = 8  # Client -> Server: Request guild member list
    INVALID_SESSION = 9  # Server -> Client: Session is invalid
    HELLO = 10  # Server -> Client: Sent on connect, contains heartbeat_interval
    HEARTBEAT_ACK = 11  # Server -> Client: Acknowledgement of heartbeat


# =============================================================================
# Gateway Intents
# Bit flags that tell the gateway which events you want to receive.
# =============================================================================


class Intents(enum.IntFlag):
    """Gateway intents control which events your bot receives.

    Usage:
        intents = Intents.GUILDS | Intents.GUILD_MESSAGES
        intents = Intents.default()
        intents = Intents.all()
    """

    GUILDS = 1 << 0
    GUILD_MEMBERS = 1 << 1
    GUILD_MODERATION = 1 << 2
    GUILD_EMOJIS_AND_STICKERS = 1 << 3
    GUILD_INTEGRATIONS = 1 << 4
    GUILD_WEBHOOKS = 1 << 5
    GUILD_INVITES = 1 << 6
    GUILD_VOICE_STATES = 1 << 7
    GUILD_PRESENCES = 1 << 8
    GUILD_MESSAGES = 1 << 9
    GUILD_MESSAGE_REACTIONS = 1 << 10
    GUILD_MESSAGE_TYPING = 1 << 11
    DIRECT_MESSAGES = 1 << 12
    DIRECT_MESSAGE_REACTIONS = 1 << 13
    DIRECT_MESSAGE_TYPING = 1 << 14
    MESSAGE_CONTENT = 1 << 15

    @classmethod
    def default(cls) -> Intents:
        """Returns a sensible default set of intents (excludes privileged ones)."""
        value = cls(0)
        for intent in cls:
            if intent not in (
                cls.GUILD_MEMBERS,
                cls.GUILD_PRESENCES,
                cls.MESSAGE_CONTENT,
            ):
                value |= intent
        return value

    @classmethod
    def all(cls) -> Intents:
        """Returns all intents enabled."""
        value = cls(0)
        for intent in cls:
            value |= intent
        return value

    @classmethod
    def none(cls) -> Intents:
        """Returns no intents."""
        return cls(0)


# =============================================================================
# Gateway Close Codes
# =============================================================================


class GatewayCloseCode(enum.IntEnum):
    """WebSocket close codes the Fluxer gateway may send."""

    UNKNOWN_ERROR = 4000
    UNKNOWN_OPCODE = 4001
    DECODE_ERROR = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    INVALID_SEQ = 4007
    RATE_LIMITED = 4008
    SESSION_TIMED_OUT = 4009
    INVALID_SHARD = 4010
    SHARDING_REQUIRED = 4011
    INVALID_API_VERSION = 4012
    INVALID_INTENTS = 4013
    DISALLOWED_INTENTS = 4014

    @property
    def is_reconnectable(self) -> bool:
        """Whether the bot should attempt to reconnect after this close code."""
        non_reconnectable = {
            self.AUTHENTICATION_FAILED,
            self.INVALID_SHARD,
            self.SHARDING_REQUIRED,
            self.INVALID_API_VERSION,
            self.INVALID_INTENTS,
            self.DISALLOWED_INTENTS,
        }
        return self not in non_reconnectable


# =============================================================================
# Channel Types
# =============================================================================


class ChannelType(enum.IntEnum):
    GUILD_TEXT = 0
    DM = 1
    GUILD_VOICE = 2
    GROUP_DM = 3
    GUILD_CATEGORY = 4
    GUILD_ANNOUNCEMENT = 5


# =============================================================================
# Permissions
# =============================================================================


class Permissions(enum.IntFlag):
    """Permission bitfield flags for guild roles and channel overwrites.

    Each member maps to a single bit in the permission integer stored on a
    role or channel overwrite.  Use bitwise operators to combine or test flags:

        Permissions.SEND_MESSAGES | Permissions.READ_MESSAGE_HISTORY
        bool(role_permissions & Permissions.ADMINISTRATOR)
    """

    # -- General --
    CREATE_INVITE = 1 << 0
    KICK_MEMBERS = 1 << 1
    BAN_MEMBERS = 1 << 2
    ADMINISTRATOR = 1 << 3
    MANAGE_CHANNELS = 1 << 4
    MANAGE_GUILD = 1 << 5
    ADD_REACTIONS = 1 << 6
    VIEW_AUDIT_LOG = 1 << 7
    PRIORITY_SPEAKER = 1 << 8
    STREAM = 1 << 9
    VIEW_CHANNEL = 1 << 10
    SEND_MESSAGES = 1 << 11
    SEND_TTS_MESSAGES = 1 << 12
    MANAGE_MESSAGES = 1 << 13
    EMBED_LINKS = 1 << 14
    ATTACH_FILES = 1 << 15
    READ_MESSAGE_HISTORY = 1 << 16
    MENTION_EVERYONE = 1 << 17
    USE_EXTERNAL_EMOJIS = 1 << 18
    USE_EXTERNAL_STICKERS = 1 << 33
    MODERATE_MEMBERS = 1 << 40
    CREATE_EXPRESSIONS = 1 << 43
    PIN_MESSAGES = 1 << 51
    BYPASS_SLOWMODE = 1 << 52
    UPDATE_RTC_REGION = 1 << 53

    # -- Voice --
    CONNECT = 1 << 20
    SPEAK = 1 << 21
    MUTE_MEMBERS = 1 << 22
    DEAFEN_MEMBERS = 1 << 23
    MOVE_MEMBERS = 1 << 24
    USE_VOICE_ACTIVITY_DETECTION = 1 << 25

    # -- Member management --
    CHANGE_NICKNAME = 1 << 26
    MANAGE_NICKNAMES = 1 << 27
    MANAGE_ROLES = 1 << 28
    MANAGE_WEBHOOKS = 1 << 29
    MANAGE_EXPRESSIONS = 1 << 30
