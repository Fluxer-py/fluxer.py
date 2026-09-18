"""Client lifecycle, parsed dispatches, bounded caches, and event handling.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
import uuid
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from .activity import BaseActivity
    from .voice import VoiceClient

from .enums import Intents
from ._types import UNSET, UnsetType
from .errors import GatewayNotConnected
from .events import fluxer_event_from_dispatch
from .fluxer_models import (
    SearchAuthorType,
    SearchContentType,
    SearchEmbedType,
    SearchResponse,
    SearchSortBy,
    SearchSortOrder,
    parse_search_response,
)
from .gateway import Gateway
from .http import HTTPClient
from .models import Channel, Guild, Message, User, UserProfile, VoiceState, Webhook
from .models.role import Role
from .models.member import GuildMember
from .state import ConnectionState

log = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class Client:
    """Low-level client that connects to Fluxer and dispatches events.

    This gives you full control over the gateway lifecycle.
    For command bots, use the bot class from ``fluxer.ext.commands``.

    Attributes:
        intents: Deprecated compatibility mask; it does not filter Fluxer Gateway events.
        api_url: Already-versioned REST override, or the base resolved after discovery.
        instance_url: Origin used for unauthenticated instance discovery.
        user: The bot user, available after the READY event.
        guilds: List of guilds the bot is in (populated from READY + GUILD_CREATE).
        loop: Return the active asyncio event loop.
        cached_messages: Messages currently retained by the in-memory message cache.
    """

    def __init__(
        self,
        *,
        intents: Intents | None = None,
        api_url: str | None = None,
        instance_url: str | None = None,
        max_retries: int = 5,
        retry_forever: bool = False,
        max_messages: int = 1000,
        cache_members: bool = True,
    ) -> None:
        """Initialize the client with the supplied configuration.

        Args:
            intents: Deprecated compatibility mask; Fluxer does not use intents to filter events.
            api_url: Already-versioned REST service override, including any instance path prefix.
            instance_url: Origin publishing the unauthenticated Fluxer discovery document.
            max_retries: Maximum retries after the initial request; zero disables retries.
            retry_forever: Whether replayable transient failures may retry without a ceiling.
            max_messages: Max messages used by this operation.
            cache_members: Cache members used by this operation.
        """
        if intents is not None:
            warnings.warn(
                "Intents are a deprecated compatibility option; Fluxer does not filter Gateway events by intents",
                DeprecationWarning,
                stacklevel=2,
            )
        self.intents: Intents = intents if intents is not None else Intents.default()
        self.api_url: str | None = api_url
        self.instance_url: str | None = instance_url
        self._http: HTTPClient | None = None
        self._gateway: Gateway | None = None
        self._event_handlers: dict[str, list[EventHandler]] = {}
        self._handler_tasks: set[asyncio.Task[None]] = set()
        self._user: User | None = None
        self._users: dict[int, User] = {}
        self._state = ConnectionState(
            max_messages=max_messages, cache_members=cache_members
        )
        self._guilds = self._state.guilds
        self._channels = self._state.channels
        self._voice_states = self._state.voice_states
        self._voice_tombstones: dict[tuple[int, int, str | None], VoiceState] = {}
        self._pending_voice: dict[int, VoiceClient] = {}
        self._active_voice: dict[int, VoiceClient] = {}
        self._voice_mutations: dict[str, VoiceClient] = {}
        self._closed: bool = False
        self._ready = asyncio.Event()
        self._waiters: dict[
            str, list[tuple[asyncio.Future[Any], Callable[..., bool] | None]]
        ] = {}
        self._max_retries = max_retries
        self._retry_forever = retry_forever

    @property
    def user(self) -> User | None:
        """The bot user, available after the READY event.

        Returns:
            The result of this operation.
        """
        return self._user

    @property
    def guilds(self) -> list[Guild]:
        """List of guilds the bot is in (populated from READY + GUILD_CREATE).

        Returns:
            The result of this operation.
        """
        return list(self._guilds.values())

    def is_ready(self) -> bool:
        """Return whether the READY event has been received.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self._ready.is_set()

    def is_closed(self) -> bool:
        """Return whether the client has been closed.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self._closed

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Return the active asyncio event loop.

        Returns:
            The result of this operation.
        """
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()

    async def wait_until_ready(self) -> None:
        """Wait until the client has received READY from the gateway.

        Returns:
            None.
        """
        await self._ready.wait()

    async def wait_for(
        self,
        event: str,
        *,
        check: Callable[..., bool] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Wait until a Fluxer event matching `check` is dispatched.

        Args:
            event: Event name used for registration or webhook callback headers.
            check: Condition used to select a message or accept an event.
            timeout: Maximum seconds to wait before raising a timeout error.

        Returns:
            The result of this operation.
        """
        event_name = event[3:] if event.startswith("on_") else event
        future: asyncio.Future[Any] = self.loop.create_future()
        waiter = (future, check)
        self._waiters.setdefault(event_name, []).append(waiter)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            waiters = self._waiters.get(event_name)
            if waiters and waiter in waiters:
                waiters.remove(waiter)
            if waiters == []:
                self._waiters.pop(event_name, None)

    def get_guild(self, id: int | str) -> Guild | None:
        """Get guild.

        Args:
            id: Identity of the object used by this operation.

        Returns:
            The requested guild, or None when no matching value is available.
        """
        try:
            return self._guilds.get(int(id))
        except (TypeError, ValueError):
            return None

    def get_channel(self, id: int | str) -> Channel | None:
        """Return a cached channel by ID, if available.

        Args:
            id: Identity of the object used by this operation.

        Returns:
            The requested channel, or None when no matching value is available.
        """
        try:
            return self._channels.get(int(id))
        except (TypeError, ValueError):
            return None

    def get_member(
        self, guild_id: int | str | None, user_id: int | str
    ) -> GuildMember | None:
        """Return a cached guild member by guild and user ID, if available.

        Args:
            guild_id: Identity of the guild used by this operation.
            user_id: Identity of the user used by this operation.

        Returns:
            The requested member, or None when no matching value is available.
        """
        try:
            guild_key = int(guild_id) if guild_id is not None else None
            user_key = int(user_id)
        except (TypeError, ValueError):
            return None
        return self._state.get_member(guild_key, user_key)

    def get_message(self, message_id: int | str | None) -> Message | None:
        """Return a cached message by ID, if available.

        Args:
            message_id: Identity of the message used by this operation.

        Returns:
            The requested message, or None when no matching value is available.
        """
        return self._state.get_message(message_id)

    @property
    def cached_messages(self) -> list[Message]:
        """Messages currently retained by the in-memory message cache.

        Returns:
            The result of this operation.
        """
        return list(self._state.messages.values())

    # =========================================================================
    # Event registration
    # =========================================================================

    def event(self, func: EventHandler) -> EventHandler:
        """Decorator to register an event handler.

        The function name determines the event:
            @bot.event
            async def on_message(message):
                ...

        Supported events (mapped from gateway dispatch names):
            on_ready       -> READY
            on_message      -> MESSAGE_CREATE
            on_message_edit -> MESSAGE_UPDATE
            on_message_delete -> MESSAGE_DELETE
            on_guild_join   -> GUILD_CREATE
            on_guild_remove -> GUILD_DELETE
            on_member_join  -> GUILD_MEMBER_ADD
            on_member_remove -> GUILD_MEMBER_REMOVE
            ... and any other gateway event as on_{lowercase_name}

        Args:
            func: Callable registered or applied by this helper.

        Returns:
            The result of this operation.
        """
        event_name = func.__name__
        if not event_name.startswith("on_"):
            raise ValueError(f"Event handler must start with 'on_', got '{event_name}'")

        self.add_listener(func)
        return func

    def on(self, event_name: str) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register an event handler with an explicit name.

        Usage:
            @bot.on("message")
            async def handle_msg(message):
                ...

        Args:
            event_name: Event name dispatched to registered callbacks.

        Returns:
            The configured decorator or callback wrapper.
        """

        def decorator(func: EventHandler) -> EventHandler:
            self.add_listener(func, f"on_{event_name}")
            return func

        return decorator

    def add_listener(self, func: EventHandler, name: str | None = None) -> None:
        """Register an event callback under its name or an explicit event name.

        Args:
            func: Coroutine callback to register.
            name: Event handler name, such as ``on_message``.
        """
        self._event_handlers.setdefault(name or func.__name__, []).append(func)

    def remove_listener(self, func: EventHandler, name: str | None = None) -> None:
        """Remove a previously registered event callback.

        Args:
            func: Coroutine callback to remove.
            name: Event handler name used during registration.
        """
        handlers = self._event_handlers.get(name or func.__name__)
        if handlers and func in handlers:
            handlers.remove(func)

    def listen(self, name: str | None = None) -> Callable[[EventHandler], EventHandler]:
        """Return a decorator that registers an event callback.

        Args:
            name: Event handler name, or the callback name when omitted.

        Returns:
            A decorator that registers the callback.
        """

        def decorator(func: EventHandler) -> EventHandler:
            self.add_listener(func, name)
            return func

        return decorator

    def dispatch(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Schedule registered handlers for a manually dispatched event.

        Args:
            event_name: Registered handler name.
            *args: Positional callback arguments.
            **kwargs: Keyword callback arguments.
        """
        for handler in tuple(self._event_handlers.get(event_name, ())):
            self.loop_create_task(
                self._run_event_handler(event_name, handler, *args, **kwargs)
            )

    def loop_create_task(self, coro: Awaitable[Any]) -> None:
        """Schedule an awaitable on the running event loop.

        Args:
            coro: Awaitable to schedule.
        """
        asyncio.ensure_future(coro)

    async def _run_event_handler(
        self, event_name: str, handler: EventHandler, *args: Any, **kwargs: Any
    ) -> None:
        """Run one handler and report its errors without stopping dispatch."""
        try:
            await handler(*args, **kwargs)
        except Exception:
            log.exception("Error in event handler '%s'", event_name)

    # =========================================================================
    # Event dispatching
    # =========================================================================

    async def _dispatch(self, event_name: str, data: Any) -> None:
        """Called by the Gateway when a dispatch event is received.

        This method:
        1. Parses the raw data into model objects
        2. Updates internal caches
        3. Fires matching user event handlers
        """
        # Map gateway event names to handler names and parse data
        match event_name:
            case "READY":
                self._state.guilds.clear()
                self._state.channels.clear()
                self._state.members.clear()
                self._state.messages.clear()
                self._state.voice_states.clear()
                self._voice_tombstones.clear()
                self._user = User.from_data(data["user"], self._http)
                self._users = {
                    int(u["id"]): User.from_data(u, self._http)
                    for u in data.get("users", [])
                }
                self._users[self._user.id] = self._user
                if self._http is not None:
                    self._http._user_id = self._user.id
                # Process guilds from READY
                for guild_data in data.get("guilds", []):
                    guild = Guild.from_data(guild_data, self._http)
                    self._state.store_guild(guild)
                    for channel in guild.channels:
                        self._state.store_channel(channel)
                    for member_data in guild_data.get("members", []):
                        self._store_member(member_data, guild.id)
                    self._seed_guild_voice_states(
                        guild.id, guild_data.get("voice_states", [])
                    )
                for channel_data in data.get("private_channels", []):
                    self._state.store_channel(
                        Channel.from_data(channel_data, self._http)
                    )
                self._ready.set()
                await self._fire("on_ready")

            case "MESSAGE_CREATE":
                message = self._parse_message(data)
                await self._fire("on_message", message)

            case "MESSAGE_UPDATE":
                message = self._parse_message(data)
                await self._fire("on_message_edit", message)

            case "MESSAGE_DELETE":
                self._state.remove_message(data["id"])
                await self._fire("on_message_delete", data)

            case "MESSAGE_DELETE_BULK":
                for message_id in data.get("ids", []):
                    self._state.remove_message(message_id)
                await self._fire("on_message_delete_bulk", data)

            case "GUILD_CREATE" | "GUILD_SYNC" | "GUILD_UPDATE":
                guild = self._replace_guild_snapshot(data)
                if event_name == "GUILD_CREATE":
                    await self._fire("on_guild_join", guild)
                else:
                    await self._fire(f"on_{event_name.lower()}", data)
                    await self._fire(
                        "on_fluxer_event", fluxer_event_from_dispatch(event_name, data)
                    )

            case "GUILD_DELETE":
                guild_id = int(data["id"])
                guild = self._guilds.get(guild_id)
                if data.get("unavailable", False):
                    if guild is None:
                        guild = Guild.from_data(data, self._http)
                        self._state.store_guild(guild)
                    guild.unavailable = True
                else:
                    self._guilds.pop(guild_id, None)
                    for channel_id in [
                        key
                        for key, ch in self._channels.items()
                        if ch.guild_id == guild_id
                    ]:
                        self._channels.pop(channel_id)
                    for key in [
                        key for key in self._state.members if key[0] == guild_id
                    ]:
                        self._state.members.pop(key)
                    for message_id, message in list(self._state.messages.items()):
                        if message.guild_id == guild_id:
                            self._state.remove_message(message_id)
                    self._voice_states.pop(guild_id, None)
                    self._clear_voice_tombstones(guild_id)
                await self._fire("on_guild_remove", guild or data)

            case "GUILD_MEMBER_ADD":
                self._store_member(data, int(data["guild_id"]))
                await self._fire("on_member_join", data)

            case "GUILD_MEMBER_REMOVE":
                self._state.members.pop(
                    (int(data["guild_id"]), int(data["user"]["id"])), None
                )
                await self._fire("on_member_remove", data)

            case "GUILD_MEMBER_UPDATE":
                self._store_member(data, int(data["guild_id"]))
                await self._fire("on_guild_member_update", data)

            case "GUILD_MEMBERS_CHUNK":
                for member_data in data.get("members", []):
                    self._store_member(member_data, int(data["guild_id"]))
                await self._fire("on_guild_members_chunk", data)

            case "CHANNEL_CREATE":
                channel = Channel.from_data(data, self._http)
                if channel.guild_id is not None:
                    channel._guild = self._guilds.get(channel.guild_id)
                self._state.store_channel(channel)
                await self._fire("on_channel_create", channel)

            case "CHANNEL_UPDATE":
                channel = Channel.from_data(data, self._http)
                if channel.guild_id is not None:
                    channel._guild = self._guilds.get(channel.guild_id)
                self._state.store_channel(channel)
                await self._fire("on_channel_update", channel)

            case "CHANNEL_DELETE":
                # CHANNEL_DELETE only provides minimal data (guild_id, id)
                # Try to get the full channel from cache before removing it
                channel_id = int(data["id"])
                channel = self._channels.pop(channel_id, None)

                if channel:
                    # We have the full channel object from cache
                    await self._fire("on_channel_delete", channel)
                else:
                    # Channel wasn't cached, fire event with raw data
                    await self._fire("on_channel_delete", data)

            case "VOICE_STATE_UPDATE":
                voice_state = self._store_voice_state(data)
                await self._fire("on_voice_state_update", voice_state)

            case "VOICE_SERVER_UPDATE":
                if data.get("guild_id") is None:
                    return
                guild_id = int(data["guild_id"])
                vc = self._pending_voice.get(guild_id) or self._active_voice.get(
                    guild_id
                )
                if vc is not None and int(data["channel_id"]) == vc.channel_id:
                    if data.get("connection_id") is not None:
                        vc._connection_id = data["connection_id"]
                    if data.get("e2ee_key") is not None:
                        vc._reject_placement(
                            "This voice integration cannot consume an encrypted grant"
                        )
                    elif data.get("connection_id") is not None:
                        await vc._on_voice_server_update(
                            data["endpoint"], data["token"], data["connection_id"]
                        )

            case "VOICE_STATE_ACK":
                vc = self._voice_mutations.get(data.get("mutation_id", ""))
                if vc is not None and data.get("error_code"):
                    vc._reject_placement(
                        f"Voice placement rejected: {data['error_code']}"
                    )
                await self._fire("on_voice_state_ack", data)

            case "RESUMED":
                await self._fire("on_resumed")

            case "MESSAGE_REACTION_ADD":
                await self._handle_reaction_add(data)

            case "MESSAGE_REACTION_REMOVE":
                await self._handle_reaction_remove(data)

            case "MESSAGE_REACTION_REMOVE_ALL":
                await self._handle_reaction_remove_all(data)

            case "MESSAGE_REACTION_REMOVE_EMOJI":
                await self._handle_reaction_remove_emoji(data)

            case "CHANNEL_UPDATE_BULK":
                for channel_data in data.get("channels", []):
                    channel = Channel.from_data(channel_data, self._http)
                    if channel.guild_id is not None:
                        channel._guild = self._guilds.get(channel.guild_id)
                    self._state.store_channel(channel)
                await self._fire(
                    "on_fluxer_event", fluxer_event_from_dispatch(event_name, data)
                )

            case "GUILD_ROLE_UPDATE_BULK":
                guild_id = int(data["guild_id"])
                guild = self._guilds.get(guild_id)
                if guild is not None:
                    roles = {role.id: role for role in guild.roles}
                    for role_data in data.get("roles", []):
                        role = Role.from_data(role_data, self._http, guild_id)
                        roles[role.id] = role
                    guild.roles = list(roles.values())
                await self._fire(
                    "on_fluxer_event", fluxer_event_from_dispatch(event_name, data)
                )

            case _:
                # Unknown/unhandled event — fire a generic handler
                handler_name = f"on_{event_name.lower()}"
                await self._fire(handler_name, data)
                await self._fire(
                    "on_fluxer_event", fluxer_event_from_dispatch(event_name, data)
                )

    def _replace_guild_snapshot(self, data: dict[str, Any]) -> Guild:
        """Replace supplied guild collections and rebind retained cache entries."""
        guild = Guild.from_data(data, self._http)
        previous = self._guilds.get(guild.id)
        if previous is not None:
            for name in ("roles", "channels", "members", "emojis", "stickers"):
                if name not in data:
                    setattr(guild, name, getattr(previous, name))
        self._state.store_guild(guild)
        if "channels" in data:
            for channel_id, channel in list(self._channels.items()):
                if channel.guild_id == guild.id:
                    self._channels.pop(channel_id)
            for channel in guild.channels:
                self._state.store_channel(channel)
        for channel in self._channels.values():
            if channel.guild_id == guild.id:
                channel._guild = guild
        if "members" in data:
            for key in list(self._state.members):
                if key[0] == guild.id:
                    self._state.members.pop(key)
            guild.members = [
                self._store_member(item, guild.id) for item in data["members"]
            ]
        if "voice_states" in data:
            self._voice_states.pop(guild.id, None)
            self._clear_voice_tombstones(guild.id)
            self._seed_guild_voice_states(guild.id, data["voice_states"])
        for message in self._state.messages.values():
            if message.guild_id == guild.id:
                message._cache_guild(guild)
                message._channel = self._channels.get(message.channel_id)
        return guild

    def _store_member(self, data: dict[str, Any], guild_id: int) -> GuildMember:
        member = GuildMember.from_data(data, self._http, guild_id=guild_id)
        if not member.user.username and member.user.id in self._users:
            member.user = self._users[member.user.id]
        else:
            self._users[member.user.id] = member.user
        return self._state.store_member(member)

    def _parse_message(self, data: dict[str, Any]) -> Message:
        """Parse message data and attach cached channel and guild references."""
        msg = Message.from_data(data, self._http)
        # Attach cached channel
        cached_channel = self._channels.get(msg.channel_id)
        if cached_channel:
            msg._channel = cached_channel
        # Resolve guild_id via channel if not present in message data
        guild_id = msg.guild_id or (cached_channel.guild_id if cached_channel else None)
        if guild_id is not None:
            cached_guild = self._guilds.get(guild_id)
            if cached_guild:
                msg._cache_guild(cached_guild)
        if data.get("member") is not None and guild_id is not None:
            msg.member = self._store_member(
                {**data["member"], "user": data["author"]}, guild_id
            )
        return self._state.store_message(msg)

    async def _handle_reaction_add(self, data: dict[str, Any]) -> None:
        """Handle MESSAGE_REACTION_ADD event."""
        from .models.reaction import RawReactionActionEvent

        raw = RawReactionActionEvent.from_data(data, "REACTION_ADD")

        message = self._state.get_message(raw.message_id)
        if message is not None:
            reaction = message._add_reaction(data, raw.emoji, raw.user_id)
            if self.user is not None and raw.user_id == self.user.id:
                reaction.me = True
        await self._fire("on_raw_reaction_add", raw)

    async def _handle_reaction_remove(self, data: dict[str, Any]) -> None:
        """Handle MESSAGE_REACTION_REMOVE event."""
        from .models.reaction import RawReactionActionEvent

        raw = RawReactionActionEvent.from_data(data, "REACTION_REMOVE")

        # Fire raw event (always fires, even if message not cached)
        message = self._state.get_message(raw.message_id)
        if message is not None:
            try:
                message._remove_reaction(data, raw.emoji, raw.user_id)
            except ValueError:
                pass
        await self._fire("on_raw_reaction_remove", raw)

    async def _handle_reaction_remove_all(self, data: dict[str, Any]) -> None:
        """Handle MESSAGE_REACTION_REMOVE_ALL event."""
        from .models.reaction import RawReactionClearEvent

        raw = RawReactionClearEvent.from_data(data)

        # Fire raw event (always fires, even if message not cached)
        message = self._state.get_message(raw.message_id)
        if message is not None:
            message.reactions.clear()
        await self._fire("on_raw_reaction_clear", raw)

    async def _handle_reaction_remove_emoji(self, data: dict[str, Any]) -> None:
        """Handle MESSAGE_REACTION_REMOVE_EMOJI event."""
        from .models.reaction import RawReactionClearEmojiEvent

        raw = RawReactionClearEmojiEvent.from_data(data)

        # Fire raw event (always fires, even if message not cached)
        message = self._state.get_message(raw.message_id)
        if message is not None:
            message._clear_emoji(raw.emoji)
        await self._fire("on_raw_reaction_clear_emoji", raw)

    async def _fire(self, event_name: str, *args: Any) -> None:
        """Fire all registered handlers for an event."""
        self._dispatch_waiters(event_name, *args)

        for handler in tuple(self._event_handlers.get(event_name, ())):
            task = asyncio.create_task(
                self._run_event_handler(event_name, handler, *args)
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)
        # Start callbacks without letting a callback awaiting another event block receiving it.
        await asyncio.sleep(0)

    def _dispatch_waiters(self, event_name: str, *args: Any) -> None:
        waiter_name = event_name[3:] if event_name.startswith("on_") else event_name
        waiters = self._waiters.get(waiter_name)
        if not waiters:
            return

        result = args[0] if len(args) == 1 else args
        remaining = []
        for future, check in waiters:
            if future.cancelled() or future.done():
                continue
            try:
                passed = check is None or check(*args)
            except Exception as exc:
                future.set_exception(exc)
                continue
            if passed:
                future.set_result(result)
            else:
                remaining.append((future, check))

        if remaining:
            self._waiters[waiter_name] = remaining
        else:
            self._waiters.pop(waiter_name, None)

    # =========================================================================
    # HTTP convenience methods
    # =========================================================================

    async def fetch_channel(self, channel_id: str) -> Channel:
        """Fetch a channel from the API (not cache).

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            The requested channel.
        """
        assert self._http is not None
        data = await self._http.get_channel(channel_id)
        ch = Channel.from_data(data, self._http)
        self._state.store_channel(ch)
        return ch

    async def fetch_message(self, channel_id: str, message_id: str) -> Message:
        """Fetch a message from the API by channel ID and message ID.

        Args:
            channel_id: Identity of the channel used by this operation.
            message_id: Identity of the message used by this operation.

        Returns:
            The requested message.
        """
        assert self._http is not None
        data = await self._http.get_message(channel_id, message_id)
        return self._parse_message(data)

    async def search_messages(
        self,
        *,
        context_channel_id: int | str | None = None,
        context_guild_id: int | str | None = None,
        channel_ids: list[int | str] | None = None,
        channel_id: list[int | str] | None = None,
        hits_per_page: int | None = None,
        page: int | None = None,
        cursor: list[str] | None = None,
        min_id: int | str | None = None,
        max_id: int | str | None = None,
        content: str | None = None,
        contents: list[str] | None = None,
        exact_phrases: list[str] | None = None,
        exclude_channel_id: list[int | str] | None = None,
        author_id: list[int | str] | None = None,
        exclude_author_id: list[int | str] | None = None,
        author_type: list[SearchAuthorType] | None = None,
        exclude_author_type: list[SearchAuthorType] | None = None,
        mentions: list[int | str] | None = None,
        exclude_mentions: list[int | str] | None = None,
        mention_everyone: bool | None = None,
        pinned: bool | None = None,
        has: list[SearchContentType] | None = None,
        exclude_has: list[SearchContentType] | None = None,
        embed_type: list[SearchEmbedType] | None = None,
        exclude_embed_type: list[SearchEmbedType] | None = None,
        embed_provider: list[str] | None = None,
        exclude_embed_provider: list[str] | None = None,
        link_hostname: list[str] | None = None,
        exclude_link_hostname: list[str] | None = None,
        attachment_filename: list[str] | None = None,
        exclude_attachment_filename: list[str] | None = None,
        attachment_extension: list[str] | None = None,
        exclude_attachment_extension: list[str] | None = None,
        sort_by: SearchSortBy | None = None,
        sort_order: SearchSortOrder | None = None,
        include_nsfw: bool | None = None,
    ) -> SearchResponse:
        """Search messages in one guild or channel using this bot client.

        Bots can only use Fluxer's `current` scope. A guild context takes
        precedence if both context IDs are supplied.

        Args:
            context_channel_id: Identity of the context channel used by this operation.
            context_guild_id: Identity of the context guild used by this operation.
            channel_ids: IDs of the channel resources selected by this operation.
            channel_id: Identity of the channel used by this operation.
            hits_per_page: Maximum search hits requested in one result page.
            page: Page number passed to the search operation.
            cursor: Opaque search continuation values from the preceding result.
            min_id: Lower message-ID bound for search results.
            max_id: Upper message-ID bound for search results.
            content: Text content sent in the message.
            contents: Contents used by this operation.
            exact_phrases: Exact phrases used by this operation.
            exclude_channel_id: Identity of the exclude channel used by this operation.
            author_id: Identity of the author used by this operation.
            exclude_author_id: Identity of the exclude author used by this operation.
            author_type: Author type used by this operation.
            exclude_author_type: Author type values excluded from search results.
            mentions: Mentions used by this operation.
            exclude_mentions: Mentions values excluded from search results.
            mention_everyone: Mention everyone used by this operation.
            pinned: Pinned used by this operation.
            has: Has used by this operation.
            exclude_has: Has values excluded from search results.
            embed_type: Embed type used by this operation.
            exclude_embed_type: Embed type values excluded from search results.
            embed_provider: Embed provider used by this operation.
            exclude_embed_provider: Embed provider values excluded from search results.
            link_hostname: Link hostname used by this operation.
            exclude_link_hostname: Link hostname values excluded from search results.
            attachment_filename: Attachment filename used by this operation.
            exclude_attachment_filename: Attachment filename values excluded from search results.
            attachment_extension: Attachment extension used by this operation.
            exclude_attachment_extension: Attachment extension values excluded from search results.
            sort_by: Sort by used by this operation.
            sort_order: Sort order used by this operation.
            include_nsfw: Whether the search may include mature content accessible to the caller.

        Returns:
            The result of this operation.
        """
        if context_channel_id is None and context_guild_id is None:
            raise ValueError("A context_channel_id or context_guild_id is required")
        assert self._http is not None
        data = await self._http.search_messages(
            scope="current",
            context_channel_id=context_channel_id,
            context_guild_id=context_guild_id,
            channel_ids=channel_ids,
            channel_id=channel_id,
            hits_per_page=hits_per_page,
            page=page,
            cursor=cursor,
            min_id=min_id,
            max_id=max_id,
            content=content,
            contents=contents,
            exact_phrases=exact_phrases,
            exclude_channel_id=exclude_channel_id,
            author_id=author_id,
            exclude_author_id=exclude_author_id,
            author_type=author_type,
            exclude_author_type=exclude_author_type,
            mentions=mentions,
            exclude_mentions=exclude_mentions,
            mention_everyone=mention_everyone,
            pinned=pinned,
            has=has,
            exclude_has=exclude_has,
            embed_type=embed_type,
            exclude_embed_type=exclude_embed_type,
            embed_provider=embed_provider,
            exclude_embed_provider=exclude_embed_provider,
            link_hostname=link_hostname,
            exclude_link_hostname=exclude_link_hostname,
            attachment_filename=attachment_filename,
            exclude_attachment_filename=exclude_attachment_filename,
            attachment_extension=attachment_extension,
            exclude_attachment_extension=exclude_attachment_extension,
            sort_by=sort_by,
            sort_order=sort_order,
            include_nsfw=include_nsfw,
        )
        return parse_search_response(data, self._http)

    async def delete_message(
        self, channel_id: int | str, message_id: int | str
    ) -> None:
        """Delete a message by channel ID and message ID without fetching it first.

        Args:
            channel_id: The channel ID where the message is located.
            message_id: The message ID to delete.

        Example:
            await client.delete_message(channel_id=123456, message_id=789012)

        Returns:
            None.
        """
        assert self._http is not None
        await self._http.delete_message(channel_id, message_id)

    async def fetch_guild(self, guild_id: str) -> Guild:
        """Fetch a guild from the API.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild.
        """
        assert self._http is not None
        data = await self._http.get_guild(guild_id)
        guild = Guild.from_data(data, self._http)
        self._state.store_guild(guild)
        return guild

    async def fetch_user(self, user_id: str) -> User:
        """Fetch a user from the API.

        Args:
            user_id: Identity of the user used by this operation.

        Returns:
            The requested user.
        """
        assert self._http is not None
        data = await self._http.get_user(user_id)
        return User.from_data(data, self._http)

    async def fetch_user_profile(
        self, user_id: str, *, guild_id: str | None = None
    ) -> UserProfile:
        """Fetch a user's full profile from the API.

        This returns additional profile information like bio, pronouns, banner, etc.
        that is not included in the basic user object.

        Args:
            user_id: The user ID to fetch
            guild_id: Optional guild ID for guild-specific profile data

        Returns:
            UserProfile containing the user and their profile information
        """
        assert self._http is not None
        data = await self._http.get_user_profile(user_id, guild_id=guild_id)
        return UserProfile.from_data(
            data, self._http, guild_id=int(guild_id) if guild_id is not None else None
        )

    async def fetch_webhook(self, webhook_id: str) -> Webhook:
        """Fetch a webhook from the API.

        Args:
            webhook_id: Identity of the webhook used by this operation.

        Returns:
            The requested webhook.
        """
        assert self._http is not None
        data = await self._http.get_webhook(webhook_id)
        return Webhook.from_data(data, self._http)

    async def fetch_channel_webhooks(self, channel_id: str) -> list[Webhook]:
        """Fetch all webhooks for a channel.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            The requested channel webhooks.
        """
        assert self._http is not None
        data = await self._http.get_channel_webhooks(channel_id)
        return [Webhook.from_data(w, self._http) for w in data]

    async def fetch_guild_webhooks(self, guild_id: str) -> list[Webhook]:
        """Fetch all webhooks for a guild.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild webhooks.
        """
        assert self._http is not None
        data = await self._http.get_guild_webhooks(guild_id)
        return [Webhook.from_data(w, self._http) for w in data]

    async def create_webhook(
        self, channel_id: str, *, name: str, avatar: str | None = None
    ) -> Webhook:
        """Create a webhook in a channel.

        Args:
            channel_id: Identity of the channel used by this operation.
            name: Name to assign or resolve in this operation.
            avatar: Replacement avatar; on an edit, omission preserves it and None clears it.

        Returns:
            The result of this operation.
        """
        assert self._http is not None
        data = await self._http.create_webhook(channel_id, name=name, avatar=avatar)
        return Webhook.from_data(data, self._http)

    # =========================================================================
    # Voice methods
    # =========================================================================

    async def join_voice(
        self,
        guild_id: int,
        channel_id: int,
        *,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> VoiceClient:
        """Join a voice channel and return a connected VoiceClient.

        Requires pip install fluxer.py[voice].

        Args:
            guild_id: Identity of the guild used by this operation.
            channel_id: Identity of the channel used by this operation.
            self_mute: Whether this voice connection starts with the local microphone muted.
            self_deaf: Whether this voice connection starts locally deafened.

        Returns:
            The result of this operation.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        from .voice import VoiceClient

        if self._gateway is None:
            raise RuntimeError("Cannot join voice before connecting")

        if guild_id in self._pending_voice or (
            guild_id in self._active_voice and self._active_voice[guild_id].is_connected
        ):
            raise RuntimeError(
                "A voice connection is already pending or active for this guild"
            )
        vc = VoiceClient(guild_id, channel_id, self._gateway)
        mutation_id = uuid.uuid4().hex
        self._pending_voice[guild_id] = vc
        self._voice_mutations[mutation_id] = vc
        try:
            await self._gateway.update_voice_state(
                guild_id=str(guild_id),
                channel_id=str(channel_id),
                self_mute=self_mute,
                self_deaf=self_deaf,
                mutation_id=mutation_id,
            )
            await vc._wait_until_connected()
        except BaseException:
            await vc.disconnect()
            raise
        else:
            self._active_voice[guild_id] = vc
            return vc
        finally:
            self._pending_voice.pop(guild_id, None)
            self._voice_mutations.pop(mutation_id, None)

    def get_voice_state(self, guild_id: int, user_id: int) -> VoiceState | None:
        """Return the cached voice state for a user in a guild, or None.

        Args:
            guild_id: Identity of the guild used by this operation.
            user_id: Identity of the user used by this operation.

        Returns:
            The requested voice state, or None when no matching value is available.
        """
        guild_states = self._voice_states.get(int(guild_id), {})
        for (cached_user_id, _connection_id), state in guild_states.items():
            if cached_user_id == int(user_id):
                return state
        return None

    def get_guild_voice_states(self, guild_id: int) -> list[VoiceState]:
        """Return all cached voice states for a guild.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild voice states.
        """
        return list(self._voice_states.get(int(guild_id), {}).values())

    def get_channel_voice_states(self, channel_id: int | str) -> list[VoiceState]:
        """Return all cached voice states for a voice channel.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            The requested channel voice states.
        """
        target_channel_id = int(channel_id)
        return [
            state
            for guild_states in self._voice_states.values()
            for state in guild_states.values()
            if state.channel_id == target_channel_id
        ]

    def get_channel_voice_user_count(self, channel_id: int | str) -> int:
        """Return the cached unique-user count for a voice channel.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            The requested channel voice user count.
        """
        return len(
            {state.user_id for state in self.get_channel_voice_states(channel_id)}
        )

    def _voice_state_key(self, voice_state: VoiceState) -> tuple[int, str | None]:
        assert voice_state.user_id is not None
        return (voice_state.user_id, voice_state.connection_id)

    def _seed_guild_voice_states(
        self, guild_id: int, voice_states: list[dict[str, Any]]
    ) -> None:
        for voice_state_data in voice_states:
            payload = {
                **voice_state_data,
                "guild_id": voice_state_data.get("guild_id", guild_id),
            }
            self._store_voice_state(payload)

    def _clear_voice_tombstones(self, guild_id: int) -> None:
        for key in list(self._voice_tombstones):
            if key[0] == guild_id:
                self._voice_tombstones.pop(key)

    def _store_voice_state(self, data: dict[str, Any]) -> VoiceState:
        voice_state = VoiceState.from_data(data, self._http)
        if voice_state.guild_id is not None and voice_state.user_id is not None:
            guild_states = self._voice_states.setdefault(voice_state.guild_id, {})
            key = self._voice_state_key(voice_state)
            tombstone_key = (voice_state.guild_id, *key)
            previous = guild_states.get(key) or self._voice_tombstones.get(
                tombstone_key
            )
            if (
                previous is not None
                and previous.version is not None
                and voice_state.version is not None
                and voice_state.version < previous.version
            ):
                return previous
            if voice_state.channel_id is None:
                guild_states.pop(key, None)
                self._voice_tombstones[tombstone_key] = voice_state
                if len(self._voice_tombstones) > 2048:
                    self._voice_tombstones.pop(next(iter(self._voice_tombstones)))
            else:
                self._voice_tombstones.pop(tombstone_key, None)
                guild_states[key] = voice_state
        return voice_state

    # =========================================================================
    # Reaction methods
    # =========================================================================

    async def add_reaction(
        self, channel_id: int | str, message_id: int | str, emoji: str
    ) -> None:
        """Add a reaction to a message by channel_id and message_id.

        Args:
            channel_id: The channel ID
            message_id: The message ID
            emoji: The emoji to react with (unicode string or custom emoji format)

        Raises:
            Forbidden: You don't have permission to add reactions
            NotFound: The message doesn't exist
            HTTPException: Adding the reaction failed

        Returns:
            None.
        """
        assert self._http is not None
        await self._http.add_reaction(channel_id, message_id, emoji)

    async def remove_reaction(
        self,
        channel_id: int | str,
        message_id: int | str,
        emoji: str,
        user_id: int | str = "@me",
    ) -> None:
        """Remove a reaction from a message by channel_id and message_id.

        Args:
            channel_id: The channel ID
            message_id: The message ID
            emoji: The emoji to remove (unicode string or custom emoji format)
            user_id: The user ID to remove the reaction from (default: @me)

        Raises:
            Forbidden: You don't have permission to remove this reaction
            NotFound: The message or reaction doesn't exist
            HTTPException: Removing the reaction failed

        Returns:
            None.
        """
        assert self._http is not None
        await self._http.delete_reaction(channel_id, message_id, emoji, user_id)

    async def clear_reactions(
        self, channel_id: int | str, message_id: int | str
    ) -> None:
        """Remove all reactions from a message.

        Args:
            channel_id: The channel ID
            message_id: The message ID

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed

        Returns:
            None.
        """
        assert self._http is not None
        await self._http.delete_all_reactions(channel_id, message_id)

    async def clear_reaction(
        self, channel_id: int | str, message_id: int | str, emoji: str
    ) -> None:
        """Remove all reactions of a specific emoji from a message.

        Args:
            channel_id: The channel ID
            message_id: The message ID
            emoji: The emoji to clear (unicode string or custom emoji format)

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed

        Returns:
            None.
        """
        assert self._http is not None
        await self._http.delete_all_reactions_for_emoji(channel_id, message_id, emoji)

    def _require_gateway(self) -> Gateway:
        if self._gateway is None or not self._gateway.is_connected:
            raise GatewayNotConnected("Gateway is not connected")
        return self._gateway

    async def change_presence(
        self,
        *,
        status: str = "online",
        activity: BaseActivity | dict[str, Any] | str | None | UnsetType = UNSET,
        afk: bool = False,
        since: float | None = None,
    ) -> None:
        """Update this client's gateway presence.

        Args:
            status: Presence status accepted by the Fluxer Gateway.
            activity: Custom status text, CustomActivity, or a custom-status mapping; None clears it.
            afk: Whether this session is away from the keyboard.
            since: Deprecated compatibility timestamp ignored by Fluxer presence updates.

        Returns:
            None.
        """
        await self._require_gateway().update_presence(
            status=status,
            activity=activity,
            afk=afk,
            since=since,
        )

    async def request_guild_members(
        self,
        guild_id: int | str,
        *,
        query: str = "",
        limit: int = 0,
        presences: bool = False,
        user_ids: list[int | str] | None = None,
        nonce: str | None = None,
    ) -> None:
        """Request guild members through the Fluxer Gateway.

        Args:
            guild_id: Identity of the guild used by this operation.
            query: Search text used to select matching members or commands.
            limit: Maximum entries in the requested page; the route's documented bounds apply.
            presences: Whether the member request asks for presence information.
            user_ids: IDs of the user resources selected by this operation.
            nonce: Caller-selected correlation value echoed by the operation when supported.

        Returns:
            None.
        """
        await self._require_gateway().request_guild_members(
            guild_id=guild_id,
            query=query,
            limit=limit,
            presences=presences,
            user_ids=user_ids,
            nonce=nonce,
        )

    async def request_lazy_members(
        self,
        guild_id: int | str,
        *,
        ranges: list[list[int]],
        channels: dict[str, Any] | None = None,
        channel_id: int | str | None = None,
    ) -> None:
        """Request a lazy member-list range through the Fluxer Gateway.

        Args:
            guild_id: Identity of the guild used by this operation.
            ranges: Inclusive member-list windows, each containing at most 100 positions.
            channels: Explicit per-channel ranges, or one channel from which to infer the range target.
            channel_id: Concrete channel receiving ranges when no mapping is supplied.

        Returns:
            None.
        """
        await self._require_gateway().request_lazy_members(
            guild_id=guild_id,
            ranges=ranges,
            channels=channels,
            **({"channel_id": channel_id} if channel_id is not None else {}),
        )

    async def request_guild_counts(self, guild_ids: list[int | str]) -> None:
        """Request member/guild statistics through the Fluxer Gateway.

        Args:
            guild_ids: IDs of the guild resources selected by this operation.

        Returns:
            None.
        """
        await self._require_gateway().request_guild_counts(guild_ids)

    async def request_channel_member_counts(
        self, channel_ids: list[int | str], *, guild_id: int | str
    ) -> None:
        """Request channel member metrics through the Fluxer Gateway.

        Args:
            channel_ids: IDs of the channel resources selected by this operation.
            guild_id: Identity of the guild used by this operation.

        Returns:
            None.
        """
        await self._require_gateway().request_channel_member_counts(
            channel_ids, guild_id=guild_id
        )

    async def setup_hook(self) -> None:
        """Called before connecting to the gateway.

        Override this to perform setup tasks before the client starts receiving events.

        Returns:
            None.
        """

    # =========================================================================
    # Connection lifecycle
    # =========================================================================

    async def start(self, token: str) -> None:
        """Connect to Fluxer and start receiving events (async version).

        Use this if you're managing your own event loop.

        Args:
            token: Caller-supplied credential or webhook capability; keep this value secret.

        Returns:
            None.
        """
        self._closed = False
        self._ready.clear()

        self._http = HTTPClient(
            token,
            api_url=self.api_url,
            instance_url=self.instance_url,
            max_retries=self._max_retries,
            retry_forever=self._retry_forever,
        )

        self._state.http = self._http

        self._gateway = Gateway(
            http_client=self._http,
            token=token,
            intents=self.intents,
            dispatch=self._dispatch,
        )

        try:
            await self._http._ensure_session()
            await self.setup_hook()
            await self._gateway.connect()
        finally:
            await self.close()

    async def close(self) -> None:
        """Disconnect from the gateway and clean up resources.

        Returns:
            None.
        """
        self._closed = True
        self._ready.clear()
        for waiters in self._waiters.values():
            for future, _check in waiters:
                future.cancel()
        self._waiters.clear()
        handlers = [
            task for task in self._handler_tasks if task is not asyncio.current_task()
        ]
        for task in handlers:
            task.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)
        for vc in set(self._pending_voice.values()) | set(self._active_voice.values()):
            vc._reject_placement("Client closed during voice placement")
            await vc.disconnect()
        self._pending_voice.clear()
        self._active_voice.clear()
        self._voice_mutations.clear()
        if self._gateway:
            await self._gateway.close()
        if self._http:
            await self._http.close()

    def run(self, token: str) -> None:
        """Blocking call that connects to Fluxer and runs the bot.

        This is the simplest way to start your bot:
            bot.run("your_token_here")

        It creates an event loop, calls start(), and handles cleanup.

        Args:
            token: Caller-supplied credential or webhook capability; keep this value secret.

        Returns:
            None.
        """

        async def _runner() -> None:
            try:
                await self.start(token)
            except KeyboardInterrupt:
                pass
            finally:
                if not self._closed:
                    await self.close()

        try:
            asyncio.run(_runner())
        except KeyboardInterrupt:
            log.info("Bot stopped by KeyboardInterrupt")


__all__ = ("Client",)
