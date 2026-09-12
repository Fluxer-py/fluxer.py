"""Main Gateway framing, ordered dispatch processing, and supported client commands.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import warnings
from collections import deque
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .activity import CustomActivity
from ._types import UNSET, UnsetType
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from .http import HTTPClient

import aiohttp

from .enums import GatewayCloseCode, GatewayOpcode, Intents
from .errors import GatewayNotConnected

log = logging.getLogger(__name__)


class GatewayPayload:
    """Represents a Gateway payload (sent or received).

    All gateway messages follow this structure:
        op: opcode (int)
        d:  event data (dict, int, or None)
        s:  sequence number (only for op 0 DISPATCH)
        t:  event name (only for op 0 DISPATCH)



    Attributes:
        op: opcode (int)
        d:  event data (dict, int, or None)
        s:  sequence number (only for op 0 DISPATCH)
        t:  event name (only for op 0 DISPATCH)
    """

    __slots__ = ("op", "d", "s", "t")

    def __init__(
        self, op: int, d: Any = None, s: int | None = None, t: str | None = None
    ) -> None:
        """Initialize the gateway payload with the supplied configuration.

        Args:
            op: Op used by this operation.
            d: D used by this operation.
            s: S used by this operation.
            t: T used by this operation.
        """
        self.op: int = op
        self.d: Any = d
        self.s: int | None = s
        self.t: str | None = t

    @classmethod
    def from_json(cls, raw: str) -> GatewayPayload:
        """Decode JSON text into a Gateway envelope.

        Args:
            raw: JSON text received from the Gateway.

        Returns:
            A parsed GatewayPayload instance.
        """
        data = json.loads(raw)
        return cls(op=data["op"], d=data.get("d"), s=data.get("s"), t=data.get("t"))

    def to_json(self) -> str:
        """Encode the Gateway envelope as JSON text.

        Returns:
            The serialized representation with supported fields preserved.
        """
        payload: dict[str, Any] = {"op": self.op, "d": self.d}
        if self.s is not None:
            payload["s"] = self.s
        if self.t is not None:
            payload["t"] = self.t
        return json.dumps(payload)

    def __repr__(self) -> str:
        """Return a diagnostic representation of this object.

        Returns:
            The result of this operation.
        """
        op_name = (
            GatewayOpcode(self.op).name
            if self.op in GatewayOpcode.__members__.values()
            else str(self.op)
        )
        return f"<GatewayPayload op={op_name} t={self.t!r} s={self.s}>"


class Gateway:
    """Manages the WebSocket connection to the Fluxer Gateway.

    This class handles the full lifecycle: connect, heartbeat, identify,
    dispatch events, and reconnect on failure.

    Attributes:
        is_connected: Return whether the underlying connection is currently established.
    """

    def __init__(
        self,
        *,
        http_client: HTTPClient,
        token: str,
        intents: Intents,
        dispatch: Callable[[str, Any], Coroutine[Any, Any, None]],
    ) -> None:
        """Initialize the gateway with the supplied configuration.

        Args:
            http_client: Transport owning discovery and Gateway credentials.
            token: Caller-supplied credential or webhook capability; keep this value secret.
            intents: Deprecated compatibility mask; Fluxer does not use intents to filter events.
            dispatch: Dispatch used by this operation.
        """
        self._http = http_client
        self._token = token
        self._intents = intents
        self._dispatch = dispatch

        # Connection state
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._heartbeat_interval: float = 41.25
        self._sequence: int | None = None
        self._session_id: str | None = None
        self._resume_gateway_url: str | None = None
        self._disconnected_at: float | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._voice_state_task: asyncio.Task[None] | None = None
        self._voice_state_queue: asyncio.Queue[GatewayPayload] = asyncio.Queue()
        self._is_closed: bool = False
        self._last_heartbeat_ack: bool = True

        self._tasks: list[asyncio.Task[None]] = []
        self._dispatch_queue: asyncio.Queue[GatewayPayload] = asyncio.Queue(
            maxsize=2048
        )
        self._dispatch_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._sent_at: deque[float] = deque()
        self._presence_at: deque[float] = deque()

    @property
    def is_connected(self) -> bool:
        """Return whether the underlying connection is currently established.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self._ws is not None and not self._ws.closed

    @staticmethod
    def _gateway_url(url: str) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        query.update(v="1", encoding="json")
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), "")
        )

    async def connect(self) -> None:
        """Establish the gateway connection and enter the event loop.

        Returns:
            None.
        """
        gateway_data = await self._http.get_gateway()
        gateway_url = gateway_data["url"]
        ws_url = self._gateway_url(gateway_url)

        log.info("Connecting to gateway: %s", ws_url)

        self._session = aiohttp.ClientSession()
        self._is_closed = False

        while not self._is_closed:
            try:
                await self._connect_and_run(ws_url)
            except (
                aiohttp.WSServerHandshakeError,
                aiohttp.ClientError,
                asyncio.TimeoutError,
            ) as e:
                log.warning("Gateway connection error: %s. Reconnecting in 5s...", e)
                await asyncio.sleep(5)
            except Exception as e:
                log.error("Unexpected gateway error: %s", e, exc_info=True)
                await asyncio.sleep(5)

    async def _connect_and_run(self, url: str) -> None:
        """Single connection attempt: connect, handshake, then listen."""
        if (
            self._disconnected_at is not None
            and asyncio.get_running_loop().time() - self._disconnected_at >= 60.0
        ):
            self._session_id = None
            self._sequence = None
            self._resume_gateway_url = None
        connect_url = self._resume_gateway_url or url
        if self._resume_gateway_url:
            connect_url = self._gateway_url(self._resume_gateway_url)

        assert self._session is not None
        self._ws = await self._session.ws_connect(connect_url, max_msg_size=0)
        log.info("WebSocket connected")

        try:
            await self._event_loop()
        finally:
            self._disconnected_at = asyncio.get_running_loop().time()
            if self._dispatch_task is not None:
                self._dispatch_task.cancel()
                await asyncio.gather(self._dispatch_task, return_exceptions=True)
                self._dispatch_task = None
            while not self._dispatch_queue.empty():
                self._dispatch_queue.get_nowait()
                self._dispatch_queue.task_done()
            await self._stop_heartbeat()
            await self._stop_voice_state_worker()
            if self._ws and not self._ws.closed:
                await self._ws.close()

    async def _event_loop(self) -> None:
        """Main receive loop: read messages and handle opcodes."""
        if self._ws is None:
            raise GatewayNotConnected("WebSocket connection not established")

        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                payload = GatewayPayload.from_json(msg.data)
                await self._handle_payload_task(payload)

            elif msg.type == aiohttp.WSMsgType.BINARY:
                payload = GatewayPayload.from_json(msg.data.decode("utf-8"))
                await self._handle_payload_task(payload)

            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                log.info("WebSocket closing")
                break

            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.error("WebSocket error: %s", self._ws.exception())
                break

        if self._ws.close_code:
            await self._handle_close_code(self._ws.close_code)

    async def _handle_payload_task(self, payload: GatewayPayload) -> None:
        """Queue dispatches in order while keeping heartbeat acknowledgements responsive."""
        if payload.op != GatewayOpcode.DISPATCH:
            await self._handle_payload(payload)
            return
        if self._dispatch_task is None or self._dispatch_task.done():
            self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        await self._dispatch_queue.put(payload)

    async def _dispatch_loop(self) -> None:
        try:
            while True:
                payload = await self._dispatch_queue.get()
                try:
                    await self._handle_payload(payload)
                finally:
                    self._dispatch_queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(
                "Dispatch processing failed; reconnecting from the last processed sequence"
            )
            if self._ws is not None:
                await self._ws.close()

    async def _handle_payload(self, payload: GatewayPayload) -> None:
        """Route an incoming payload by opcode."""
        log.debug("Received: %s", payload)

        match payload.op:
            case GatewayOpcode.HELLO:
                self._heartbeat_interval = payload.d["heartbeat_interval"] / 1000.0
                await self._start_heartbeat()

                if self._session_id:
                    await self._send_resume()
                else:
                    await self._send_identify()

            case GatewayOpcode.HEARTBEAT_ACK:
                self._last_heartbeat_ack = True
                log.debug("Heartbeat ACK received")

            case GatewayOpcode.HEARTBEAT:
                await self._send_heartbeat()

            case GatewayOpcode.DISPATCH:
                event_name = payload.t or ""
                await self._handle_dispatch(event_name, payload.d)
                if payload.s is not None:
                    self._sequence = payload.s

            case GatewayOpcode.RECONNECT:
                log.info("Gateway requested reconnect")
                if self._ws:
                    await self._ws.close()

            case GatewayOpcode.INVALID_SESSION:
                resumable = payload.d if isinstance(payload.d, bool) else False
                log.warning("Invalid session (resumable=%s)", resumable)
                if not resumable:
                    self._session_id = None
                    self._sequence = None
                    self._resume_gateway_url = None
                await asyncio.sleep(1 + (5 * (not resumable)))
                if self._ws:
                    await self._ws.close()

    async def _handle_dispatch(self, event_name: str, data: Any) -> None:
        """Handle a DISPATCH event (op 0)."""
        match event_name:
            case "READY":
                self._session_id = data["session_id"]
                self._resume_gateway_url = data.get("resume_gateway_url")
                log.info(
                    "READY: session=%s, user=%s",
                    self._session_id,
                    data["user"].get("username", "?"),
                )

            case "RESUMED":
                log.info("Successfully resumed session")

        await self._dispatch(event_name, data)

    async def _handle_close_code(self, code: int) -> None:
        """Handle a WebSocket close code from the gateway."""
        log.info("Gateway closed with code %d", code)

        if code in (4007, 4009):
            self._session_id = None
            self._sequence = None
            self._resume_gateway_url = None
        try:
            close_code = GatewayCloseCode(code)
            if not close_code.is_reconnectable:
                log.error(
                    "Fatal close code %d (%s), not reconnecting", code, close_code.name
                )
                self._is_closed = True
        except ValueError:
            # Unknown close code, try to reconnect
            log.warning("Unknown close code %d, attempting reconnect", code)

    # =========================================================================
    # Sending
    # =========================================================================

    async def _send(self, payload: GatewayPayload) -> None:
        """Send a payload over the WebSocket."""
        if self._ws is None or self._ws.closed:
            raise ConnectionError("Tried to send on closed WebSocket")
        if payload.op in {5, 12}:
            raise ValueError("Reserved Gateway opcodes cannot be sent")
        raw = payload.to_json()
        log.debug("Sending: %s", payload)
        if len(raw.encode("utf-8")) > 4096:
            raise ValueError("Gateway payload exceeds the documented 4096-byte limit")
        while True:
            async with self._send_lock:
                now = asyncio.get_running_loop().time()
                while self._sent_at and self._sent_at[0] <= now - 60:
                    self._sent_at.popleft()
                while self._presence_at and self._presence_at[0] <= now - 20:
                    self._presence_at.popleft()
                waits = [0.0]
                ceiling = 600 if payload.op == GatewayOpcode.HEARTBEAT else 590
                if len(self._sent_at) >= ceiling:
                    waits.append(self._sent_at[0] + 60 - now)
                if (
                    payload.op == GatewayOpcode.PRESENCE_UPDATE
                    and len(self._presence_at) >= 5
                ):
                    waits.append(self._presence_at[0] + 20 - now)
                delay = max(waits)
                if delay <= 0:
                    await self._ws.send_str(raw)
                    sent = asyncio.get_running_loop().time()
                    self._sent_at.append(sent)
                    if payload.op == GatewayOpcode.PRESENCE_UPDATE:
                        self._presence_at.append(sent)
                    return
            await asyncio.sleep(delay)

    async def _send_identify(self) -> None:
        """Send the IDENTIFY payload to start a new session."""
        payload = GatewayPayload(
            op=GatewayOpcode.IDENTIFY,
            d={
                "token": self._token,
                "properties": {
                    "os": sys.platform,
                    "browser": "fluxer.py",
                    "device": "fluxer.py",
                },
            },
        )
        await self._send(payload)
        log.info("Sent IDENTIFY")

    async def _send_resume(self) -> None:
        """Send the RESUME payload to continue an existing session."""
        payload = GatewayPayload(
            op=GatewayOpcode.RESUME,
            d={
                "token": self._token,
                "session_id": self._session_id,
                "seq": self._sequence,
            },
        )
        await self._send(payload)
        log.info("Sent RESUME (session=%s, seq=%s)", self._session_id, self._sequence)

    async def _send_heartbeat(self) -> None:
        """Send a heartbeat to keep the connection alive."""
        payload = GatewayPayload(op=GatewayOpcode.HEARTBEAT, d=self._sequence)
        await self._send(payload)

    # =========================================================================
    # Heartbeat loop
    # =========================================================================

    async def _start_heartbeat(self) -> None:
        await self._stop_heartbeat()
        self._last_heartbeat_ack = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        task, self._heartbeat_task = self._heartbeat_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats. If we miss an ACK, reconnect."""
        try:
            import random

            await asyncio.sleep(self._heartbeat_interval * random.random())
            while True:
                # Check if the connection is still active
                if not self.is_connected:
                    log.debug("WebSocket disconnected, stopping heartbeat loop")
                    return

                if not self._last_heartbeat_ack:
                    log.warning(
                        "Missed heartbeat ACK, closing connection to trigger reconnect"
                    )
                    if self._ws and not self._ws.closed:
                        await self._ws.close(code=4000)
                    return

                self._last_heartbeat_ack = False
                try:
                    await self._send_heartbeat()
                except Exception as e:
                    log.warning(
                        f"Failed to send heartbeat due to exception: {e}, closing to trigger reconnect"
                    )
                    if self._ws and not self._ws.closed:
                        await self._ws.close(code=4000)
                    return
                await asyncio.sleep(self._heartbeat_interval)
        except asyncio.CancelledError:
            pass

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def close(self) -> None:
        """Gracefully close the gateway connection.

        Returns:
            None.
        """
        self._is_closed = True
        if self.is_connected and self._voice_state_task is not None:
            try:
                await asyncio.wait_for(self._voice_state_queue.join(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
        await self._stop_heartbeat()
        await self._stop_voice_state_worker()
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            await asyncio.gather(self._dispatch_task, return_exceptions=True)
            self._dispatch_task = None
        if self._ws and not self._ws.closed:
            await self._ws.close(code=1000)
        if self._session and not self._session.closed:
            await self._session.close()

    async def update_presence(
        self,
        *,
        status: str = "online",
        activity: Any | None | UnsetType = UNSET,
        activity_name: str | None = None,
        activity_type: int = 0,
        afk: bool = False,
        since: float | None = None,
    ) -> None:
        """Publish a status and optional Fluxer custom status.

        Args:
            status: Online, idle, dnd, invisible, or offline status.
            activity: CustomActivity, text, or custom-status mapping. Omission preserves; None clears.
            activity_name: Legacy text alias when activity is absent.
            activity_type: Legacy value; only custom text is publishable.
            afk: Whether this session is away.
            since: Deprecated compatibility value ignored by Fluxer.

        Raises:
            ValueError: The status or activity cannot be published by Fluxer.

        Returns:
            None.
        """
        if status not in {"online", "idle", "dnd", "invisible", "offline"}:
            raise ValueError("Unsupported Fluxer presence status")
        if since is not None:
            warnings.warn(
                "since is ignored by Fluxer presence", DeprecationWarning, stacklevel=2
            )
        if activity in (None, UNSET) and activity_name is not None:
            if activity_type not in (0, 4):
                raise ValueError(
                    "Fluxer supports custom status text, not rich activities"
                )
            activity = activity_name
        if isinstance(activity, CustomActivity):
            custom_status = {"text": activity.name}
        elif isinstance(activity, str):
            custom_status = {"text": activity}
        elif isinstance(activity, dict):
            if set(activity) - {"text", "expires_at", "emoji_id", "emoji_name"}:
                raise ValueError("Unsupported custom status fields")
            custom_status = dict(activity)
            if custom_status.get("emoji_id") is not None:
                custom_status["emoji_id"] = str(custom_status["emoji_id"])
        elif activity is None or activity is UNSET:
            custom_status = activity
        else:
            raise ValueError("Fluxer presence accepts CustomActivity or a string")
        presence: dict[str, Any] = {"status": status, "afk": afk}
        if not isinstance(custom_status, UnsetType):
            presence["custom_status"] = custom_status
        await self._send(GatewayPayload(op=GatewayOpcode.PRESENCE_UPDATE, d=presence))

    async def request_guild_members(
        self,
        *,
        guild_id: int | str,
        query: str = "",
        limit: int = 0,
        presences: bool = False,
        user_ids: list[int | str] | None = None,
        nonce: str | None = None,
    ) -> None:
        """Request a bounded member query through the Gateway.

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
        payload: dict[str, Any] = {
            "guild_id": str(guild_id),
            "query": query,
            "limit": limit,
            "presences": presences,
        }
        if user_ids is not None:
            payload["user_ids"] = [str(user_id) for user_id in user_ids]
        if nonce is not None:
            payload["nonce"] = nonce
        await self._send(
            GatewayPayload(op=GatewayOpcode.REQUEST_GUILD_MEMBERS, d=payload)
        )

    async def request_lazy_members(
        self,
        *,
        guild_id: int | str,
        ranges: list[list[int]],
        channels: dict[str, Any] | None = None,
        channel_id: int | str | None = None,
    ) -> None:
        """Set bounded channel member-list subscriptions for a guild.

        Args:
            guild_id: Identity of the guild used by this operation.
            ranges: Inclusive member-list windows, each containing at most 100 positions.
            channels: Explicit per-channel ranges, or one channel from which to infer the range target.
            channel_id: Concrete channel receiving ranges when no mapping is supplied.

        Returns:
            None.
        """
        if channel_id is not None:
            if channels is not None:
                raise ValueError("Supply channel_id or channels, not both")
            channels = {str(channel_id): ranges}
        if (
            channels
            and any(not isinstance(value, list) for value in channels.values())
            and len(channels) != 1
        ):
            raise ValueError("Range-only requests need exactly one target channel")
        if not channels:
            raise ValueError("Lazy member requests require a channel mapping")
        member_list_channels = {}
        for channel_id, channel_ranges in channels.items():
            selected = channel_ranges if isinstance(channel_ranges, list) else ranges
            if len(selected) > 10 or any(
                len(r) != 2 or not 0 <= r[0] <= r[1] <= 100000 or r[1] - r[0] > 99
                for r in selected
            ):
                raise ValueError(
                    "Each channel accepts up to ten ranges of at most 100 members"
                )
            member_list_channels[str(channel_id)] = selected
        await self._send(
            GatewayPayload(
                op=GatewayOpcode.LAZY_REQUEST,
                d={
                    "subscriptions": {
                        str(guild_id): {"member_list_channels": member_list_channels}
                    },
                },
            )
        )

    async def request_guild_counts(self, guild_ids: list[int | str]) -> None:
        """Request live counts for the selected guilds.

        Args:
            guild_ids: IDs of the guild resources selected by this operation.

        Returns:
            None.
        """
        await self._send(
            GatewayPayload(
                op=GatewayOpcode.REQUEST_GUILD_COUNTS,
                d={"guild_ids": [str(guild_id) for guild_id in guild_ids]},
            )
        )

    async def request_channel_member_counts(
        self, channel_ids: list[int | str], *, guild_id: int | str
    ) -> None:
        """Request member counts for channels in one guild.

        Args:
            channel_ids: IDs of the channel resources selected by this operation.
            guild_id: Identity of the guild used by this operation.

        Returns:
            None.
        """
        await self._send(
            GatewayPayload(
                op=GatewayOpcode.REQUEST_CHANNEL_MEMBER_COUNTS,
                d={
                    "guild_id": str(guild_id),
                    "channel_ids": list(
                        dict.fromkeys(str(channel_id) for channel_id in channel_ids)
                    )[:25],
                },
            )
        )

    async def update_voice_state(
        self,
        *,
        guild_id: str,
        channel_id: str | None = None,
        self_mute: bool = False,
        self_deaf: bool = False,
        connection_id: str | None = None,
        mutation_id: str | None = None,
    ) -> None:
        """Queue a voice placement or mutation with its connection identity.

        Args:
            guild_id: Identity of the guild used by this operation.
            channel_id: Identity of the channel used by this operation.
            self_mute: Whether this voice connection starts with the local microphone muted.
            self_deaf: Whether this voice connection starts locally deafened.
            connection_id: Connection identity issued by the voice grant, required when leaving.
            mutation_id: Correlation value identifying a voice placement acknowledgement.

        Returns:
            None.
        """
        if channel_id is None and connection_id is None:
            raise ValueError("Leaving voice requires the issued connection_id")
        payload = GatewayPayload(
            op=GatewayOpcode.VOICE_STATE_UPDATE,
            d={
                "guild_id": guild_id,
                "channel_id": channel_id,
                "self_mute": self_mute,
                "self_deaf": self_deaf,
            },
        )
        if connection_id is not None:
            payload.d["connection_id"] = connection_id
        if mutation_id is not None:
            payload.d["mutation_id"] = mutation_id
        self._start_voice_state_worker()
        await self._voice_state_queue.put(payload)

    def _start_voice_state_worker(self) -> None:
        if self._voice_state_task is None or self._voice_state_task.done():
            self._voice_state_task = asyncio.create_task(self._voice_state_loop())

    async def _stop_voice_state_worker(self) -> None:
        task, self._voice_state_task = self._voice_state_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        while not self._voice_state_queue.empty():
            self._voice_state_queue.get_nowait()
            self._voice_state_queue.task_done()

    async def _voice_state_loop(self) -> None:
        try:
            while True:
                payload = await self._voice_state_queue.get()
                try:
                    await self._send(payload)
                    await asyncio.sleep(0.5)
                finally:
                    self._voice_state_queue.task_done()
        except asyncio.CancelledError:
            pass


__all__ = ("GatewayPayload", "Gateway")
