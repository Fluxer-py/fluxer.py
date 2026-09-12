"""Asynchronous transport and existing resource operations for Fluxer.

Requests use instance discovery or an explicit REST override. The transport
preserves response variants, credential scope and rate-limit retry information.
"""

from __future__ import annotations
import asyncio
import json as json_mod
import logging
import math
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote
import aiohttp
from ._endpoints import Endpoints
from ._types import UNSET, UnsetType, PinPage
from .models.embed import Embed
from .errors import (
    HTTPException,
    RateLimited,
    Unauthorized,
    NotFound,
    http_exception_from_status,
)
from .fluxer_models import (
    SearchAuthorType,
    SearchContentType,
    SearchEmbedType,
    SearchScope,
    SearchSortBy,
    SearchSortOrder,
)

__all__ = ("HTTPClient", "Route", "RateLimiter", "DEFAULT_API_URL")
log = logging.getLogger(__name__)
DEFAULT_API_URL = "https://api.fluxer.app/v1"


def _payload_value(value: Any) -> Any:
    if isinstance(value, Embed):
        return value._to_request_dict()
    return value.to_dict() if hasattr(value, "to_dict") else value


def _get_user_agent() -> str:
    from . import __version__

    return f"fluxer.py/{__version__} (https://github.com/akarealemil/fluxer.py)"


def _delay(value: Any, fallback: float = 1.0) -> float:
    try:
        result = float(value)
        return max(0.001, result) if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback


def _multipart(
    payload: dict[str, Any], files: list[Any]
) -> Callable[[], aiohttp.FormData]:
    payload = dict(payload)
    payload["attachments"] = list(payload.get("attachments", [])) + [
        {
            "id": i,
            "filename": item["filename"],
            **(
                {"description": item["description"]}
                if item.get("description") is not None
                else {}
            ),
        }
        for i, item in enumerate(files)
    ]
    encoded = json_mod.dumps(payload)
    parts = [(item["filename"], bytes(item["data"])) for item in files]

    def build() -> aiohttp.FormData:
        form = aiohttp.FormData()
        form.add_field("payload_json", encoded, content_type="application/json")
        for i, (filename, content) in enumerate(parts):
            form.add_field(f"files[{i}]", content, filename=filename)
        return form

    return build


class Route:
    """Describe one REST operation and its resource-specific rate bucket.

    Attributes:
        method: HTTP method used for this operation.
        path: Unformatted operation path, suitable for safe diagnostics.
        base_url: Explicit service base, or None for the owning client's base.
        params: Raw path values, encoded once when constructing the URL.
        url: Resolved request URL; capability URLs must be kept secret.
        bucket: Rate-limit identity including resource parameters.
    """

    def __init__(
        self, method: str, path: str, base_url: str | None = None, **params: Any
    ) -> None:
        """Describe a route without discovering or contacting an instance.

        Args:
            method: HTTP operation name.
            path: Path template containing named placeholders.
            base_url: Already-versioned override; omitted routes use their client.
            **params: Values for the path placeholders.
        """
        self.method: str = method.upper()
        self.path: str = path
        self.base_url: str | None = base_url.rstrip("/") if base_url else None
        self.params: dict[str, str] = {k: str(v) for k, v in params.items()}
        encoded = {k: quote(v, safe="@") for k, v in self.params.items()}
        self._suffix = path.format(**encoded)
        self.url: str = (self.base_url or "") + self._suffix
        self.bucket: str = f"{self.method} {path}"
        for key in ("channel_id", "guild_id", "webhook_id"):
            if key in self.params:
                self.bucket += f":{key}={self.params[key]}"


class RateLimiter:
    """Resource-scoped request serialization and server-directed denial deadlines.

    Attributes:
        acquire: Await a resource allowance and retain ownership until release.
        release: Record response metadata and release the current task allowance.
    """

    def __init__(self) -> None:
        """Initialize empty per-resource deadlines and the global deadline.

        Note:
            Further behaviour is defined by the methods on this instance.
        """
        self._locks: dict[str, asyncio.Lock] = {}
        self._reset_times: dict[str, float] = {}
        self._global_until = 0.0
        self._owners: dict[str, asyncio.Task[Any] | None] = {}
        self._bucket_hashes: dict[str, str] = {}
        self._held: dict[str, asyncio.Lock] = {}

    def _get_lock(self, bucket: str) -> asyncio.Lock:
        return self._locks.setdefault(
            self._bucket_hashes.get(bucket, bucket), asyncio.Lock()
        )

    async def acquire(self, bucket: str) -> None:
        """Acquire a resource allowance, releasing ownership on cancellation.

        Args:
            bucket: Operation and resource identity from Route.

        Returns:
            None.
        """
        while True:
            lock = self._get_lock(bucket)
            await lock.acquire()
            if lock is self._get_lock(bucket):
                break
            lock.release()
        self._held[bucket] = lock
        self._owners[bucket] = asyncio.current_task()
        try:
            while True:
                until = max(
                    self._global_until,
                    self._reset_times.get(self._bucket_hashes.get(bucket, bucket), 0.0),
                )
                delay = until - asyncio.get_running_loop().time()
                if delay <= 0:
                    return
                await asyncio.sleep(delay)
        except BaseException:
            self.release(bucket, {})
            raise

    def release(self, bucket: str, headers: Mapping[str, str]) -> None:
        """Record response bucket metadata and release only this task's lock.

        Args:
            bucket: Previously acquired resource identity.
            headers: Case-insensitive HTTP response metadata.

        Note:
            Reset-After describes full refill, not the next admitted request.
            Denial delays are recorded separately from these informational headers.

        Returns:
            None.
        """
        if (
            self._owners.get(bucket) is not asyncio.current_task()
            or bucket not in self._owners
        ):
            return
        try:
            values = {k.lower(): v for k, v in headers.items()}
            if "x-ratelimit-bucket" in values:
                previous = self._bucket_hashes.get(bucket, bucket)
                scope = bucket.partition(":")[2]
                identity = f"{values['x-ratelimit-bucket']}:{scope}"
                self._bucket_hashes[bucket] = identity
                self._reset_times[identity] = max(
                    self._reset_times.get(previous, 0.0),
                    self._reset_times.get(identity, 0.0),
                )
        finally:
            self._owners.pop(bucket, None)
            self._held.pop(bucket).release()

    def set_global(self, retry_after: float) -> None:
        """Extend the global denial deadline without shortening another denial.

        Args:
            retry_after: Fractional seconds until another request is admitted.

        Returns:
            None.
        """
        self._global_until = max(
            self._global_until, asyncio.get_running_loop().time() + retry_after
        )

    def _deny(self, bucket: str, retry_after: float) -> None:
        identity = self._bucket_hashes.get(bucket, bucket)
        self._reset_times[identity] = max(
            self._reset_times.get(identity, 0.0),
            asyncio.get_running_loop().time() + retry_after,
        )


class HTTPClient:
    """Consume an existing bot or user token through the Fluxer HTTP API.

    Example:
        async with HTTPClient(token, instance_url="https://example.com") as http:
            user = await http.get_current_user()
            print(user["username"])

    Note:
        Retried mutations cannot guarantee exactly-once execution. User-session
        global rate limits revoke the token and are never automatically retried.

    Attributes:
        token: Caller-supplied credential, which must not be logged.
        is_bot: Whether to apply the Bot authorization prefix.
        api_url: Already-versioned REST override, or the base resolved after discovery.
        max_retries: Maximum retries after the initial attempt.
        retry_forever: Whether replayable transient failures have no retry ceiling.
    """

    def __init__(
        self,
        token: str,
        *,
        is_bot: bool = True,
        api_url: str | None = None,
        instance_url: str | None = None,
        max_retries: int = 4,
        retry_forever: bool = False,
    ) -> None:
        """Configure transport without opening a session.

        Args:
            token: Raw bot token or bare user session token.
            is_bot: Apply the bot credential scheme when true.
            api_url: Already-versioned REST override.
            instance_url: Origin publishing unauthenticated Fluxer discovery.
            max_retries: Retries permitted after the first attempt.
            retry_forever: Retry replayable transient failures indefinitely.
        """
        if max_retries < 0:
            raise ValueError("max_retries must be nonnegative")
        self.token: str = token
        self.is_bot: bool = is_bot
        self.api_url: str | None = api_url.rstrip("/") if api_url else None
        self.max_retries: int = max_retries
        self.retry_forever: bool = retry_forever
        self._endpoints = Endpoints(instance_url, api_url)
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = RateLimiter()
        self._invalidated = False
        self._user_id: int | None = None

    def _route(self, method: str, path: str, **params: Any) -> Route:
        return Route(method, path, **params)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": _get_user_agent()}
            )
        await self._endpoints.initialize(self._session)
        self.api_url = self._endpoints.api
        return self._session

    async def close(self) -> None:
        """Close the owned HTTP session.

        Repeated calls are safe, including after a failed initialization.

        Returns:
            None.
        """
        if self._session and (not self._session.closed):
            await self._session.close()

    async def __aenter__(self) -> HTTPClient:
        """Initialize discovery and return this transport.

        Returns:
            The initialized HTTP client.
        """
        try:
            await self._ensure_session()
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Release this transport's session when leaving an async context.

        Args:
            *args: Exception context supplied by the async context manager.

        Returns:
            None.
        """
        await self.close()

    async def request(
        self,
        route: Route,
        *,
        json: Any = None,
        data: aiohttp.FormData | Callable[[], aiohttp.FormData] | None = None,
        params: dict[str, Any] | None = None,
        reason: str | None = None,
        headers: Mapping[str, str] | None = None,
        max_retries: int | None = None,
        retry_forever: bool | None = None,
    ) -> Any:
        """Execute a route, preserving JSON, empty and text response variants.

        Args:
            route: Operation and resource identity.
            json: JSON body; explicit null members are preserved.
            data: Multipart body or a factory returning a fresh body for each attempt.
            params: Query parameters.
            reason: Audit reason for an operation supporting that header.
            headers: Operation-specific headers, excluding Authorization.
            max_retries: Override the client's retry ceiling.
            retry_forever: Override indefinite retries for replayable requests.

        Returns:
            Parsed JSON, a plain-text response, or None for an empty success.

        Raises:
            HTTPException: The operation failed or its retry budget was exhausted.
            Unauthorized: A previous global denial revoked the user session.
            ValueError: A successful response claimed JSON but contained invalid JSON.
        """
        capability = "token" in route.params
        if self._invalidated and (not capability):
            raise Unauthorized(
                401,
                "UNAUTHORIZED",
                "User session was revoked by a global rate limit; supply a new token",
            )
        session = await self._ensure_session()
        base = route.base_url or self.api_url
        assert base is not None
        route.url = base + route._suffix
        request_headers = dict(headers or {})
        if any((k.lower() == "authorization" for k in request_headers)):
            raise ValueError("Authorization is managed by HTTPClient")
        if not capability and base == self.api_url:
            request_headers["Authorization"] = (
                f"Bot {self.token}" if self.is_bot else self.token
            )
        if reason is not None:
            request_headers["X-Audit-Log-Reason"] = reason
        retries = self.max_retries if max_retries is None else max_retries
        if retries < 0:
            raise ValueError("max_retries must be nonnegative")
        forever = self.retry_forever if retry_forever is None else retry_forever
        replayable = data is None or callable(data)
        attempt = 0
        last_error: HTTPException | None = None
        while True:
            await self._rate_limiter.acquire(route.bucket)
            response_headers: Mapping[str, str] = {}
            retry_delay = 0.0
            error: HTTPException | None = None
            response_received = False
            try:
                async with session.request(
                    route.method,
                    route.url,
                    json=json,
                    data=data() if callable(data) else data,
                    params=params,
                    headers=request_headers,
                    allow_redirects=False,
                ) as response:
                    response_received = True
                    response_headers = response.headers
                    raw = await response.text()
                    is_json = "json" in response.headers.get("Content-Type", "").lower()
                    if 200 <= response.status < 300:
                        if not raw:
                            return None
                        if is_json:
                            return json_mod.loads(raw)
                        return raw
                    try:
                        body = json_mod.loads(raw)
                    except (ValueError, TypeError):
                        body = {}
                    if not isinstance(body, dict):
                        body = {}
                    retry_delay = _delay(
                        body.get("retry_after"),
                        _delay(response.headers.get("Retry-After")),
                    )
                    error = http_exception_from_status(
                        response.status,
                        str(body.get("code", "UNKNOWN")),
                        str(
                            body.get(
                                "message", response.reason or "HTTP request failed"
                            )
                        ),
                        errors=body.get("errors"),
                        retry_after=retry_delay,
                        global_limit=body.get("global", False),
                        raw_data=body,
                    )
                    last_error = error
                    if response.status == 429:
                        if body.get("global"):
                            self._rate_limiter.set_global(retry_delay)
                            if (
                                not self.is_bot
                                and (not capability)
                                and base == self.api_url
                                and self.token.startswith("flx_")
                            ):
                                self._invalidated = True
                                if isinstance(error, RateLimited):
                                    error.session_invalidated = True
                                raise error
                        else:
                            self._rate_limiter._deny(route.bucket, retry_delay)
                    elif response.status >= 500:
                        retry_delay = 1.0 + attempt
                    else:
                        raise error
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if (
                    response_received
                    or not replayable
                    or (not forever and attempt >= retries)
                ):
                    if last_error is not None:
                        raise last_error from None
                    raise HTTPException(
                        0,
                        "TRANSPORT_ERROR",
                        f"Transport failed for {route.method} {route.path}",
                    ) from None
                retry_delay = 1.0 + attempt
            finally:
                self._rate_limiter.release(route.bucket, response_headers)
            if not replayable or (not forever and attempt >= retries):
                assert error is not None
                raise error
            attempt += 1
            if retry_delay:
                await asyncio.sleep(retry_delay)

    async def get_gateway(self) -> dict[str, Any]:
        """Resolve a Gateway URL for the configured credential kind.

        Bot clients use the authenticated bot Gateway metadata route. User
        clients use the Gateway URL published by instance discovery.

        Returns:
            A mapping containing url, plus any bot session-start metadata.

        Raises:
            RuntimeError: A user client has no discovered Gateway service.
            HTTPException: Bot metadata retrieval fails.
        """
        if self.is_bot:
            return await self.get_gateway_bot()
        await self._ensure_session()
        return {"url": self._endpoints.base("gateway")}

    async def get_gateway_bot(self) -> dict[str, Any]:
        """GET /gateway/bot — get gateway URL + sharding info.

        Returns:
            The requested gateway bot.
        """
        return await self.request(self._route("GET", "/gateway/bot"))

    async def get_current_user(self) -> dict[str, Any]:
        """GET /users/@me.

        Returns:
            The requested current user.
        """
        return await self.request(self._route("GET", "/users/@me"))

    async def get_user(self, user_id: int | str) -> dict[str, Any]:
        """GET /users/{user_id}.

        Args:
            user_id: Identity of the user used by this operation.

        Returns:
            The requested user.
        """
        return await self.request(
            self._route("GET", "/users/{user_id}", user_id=user_id)
        )

    async def get_user_profile(
        self, user_id: int | str, *, guild_id: int | str | None = None
    ) -> dict[str, Any]:
        """GET /users/{user_id}/profile — Get a user's full profile.

        This returns additional profile information like bio, pronouns, banner, etc.
        that is not included in the basic user object.

        Args:
            user_id: The user ID to fetch
            guild_id: Optional guild ID for guild-specific profile data

        Returns:
            Profile object containing:
            - user: Basic user object
            - user_profile: Profile data (bio, pronouns, banner, etc.)
            - premium_type, premium_since, premium_lifetime_sequence
        """
        route = self._route("GET", "/users/{user_id}/profile", user_id=user_id)
        params = {"guild_id": str(guild_id)} if guild_id else None
        return await self.request(route, params=params)

    async def create_dm(self, user_id: int | str) -> dict[str, Any]:
        """POST /users/@me/channels — Open a DM channel with a user.

        Args:
            user_id: The ID of the user to open a DM with.

        Returns:
            Channel object for the DM channel.
        """
        return await self.request(
            self._route("POST", "/users/@me/channels"),
            json={"recipient_id": str(user_id)},
        )

    async def get_current_user_guilds(self) -> list[dict[str, Any]]:
        """GET /users/@me/guilds - get guilds the current user is in.

        Returns:
            The requested current user guilds.
        """
        return await self.request(self._route("GET", "/users/@me/guilds"))

    async def get_channel(self, channel_id: int | str) -> dict[str, Any]:
        """GET /channels/{channel_id}.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            The requested channel.
        """
        return await self.request(
            self._route("GET", "/channels/{channel_id}", channel_id=channel_id)
        )

    async def trigger_typing(self, channel_id: int | str) -> None:
        """Send a typing notification to the selected channel.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            None.
        """
        return await self.request(
            self._route("POST", "/channels/{channel_id}/typing", channel_id=channel_id)
        )

    async def get_channel_invites(self, channel_id: int | str) -> list[dict[str, Any]]:
        """GET /channels/{channel_id}/invites.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            The requested channel invites.
        """
        return await self.request(
            self._route("GET", "/channels/{channel_id}/invites", channel_id=channel_id)
        )

    async def create_channel_invite(
        self, channel_id: int | str, **payload: Any
    ) -> dict[str, Any]:
        """POST /channels/{channel_id}/invites.

        Args:
            channel_id: Identity of the channel used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route(
                "POST", "/channels/{channel_id}/invites", channel_id=channel_id
            ),
            json=payload,
        )

    async def send_message(
        self,
        channel_id: int | str,
        *,
        content: str | None = None,
        embed: Any | None = None,
        embeds: list[Any] | None = None,
        files: list[Any] | None = None,
        message_reference: dict[str, Any] | None = None,
        allowed_mentions: Any | None = None,
        flags: int | None = None,
        nonce: str | int | None = None,
        favorite_meme_id: int | str | None = None,
        sticker_ids: list[int | str] | None = None,
        tts: bool | None = None,
    ) -> dict[str, Any]:
        """POST /channels/{channel_id}/messages.

        Args:
            channel_id: The channel to send the message to
            content: The message content
            embed: Single embed object (optional)
            embeds: List of embed objects (Embed or dict)
            files: List of file objects to attach
            message_reference: Reference to another message for replies
                Example: {"message_id": "123456789", "channel_id": "987654321"}
            allowed_mentions: Controls which mentions trigger notifications
            flags: Bit mask governing the object's documented flags.
            nonce: Caller-selected correlation value echoed by the operation when supported.
            favorite_meme_id: Identity of the favorite meme used by this operation.
            sticker_ids: IDs of the sticker resources selected by this operation.
            tts: Whether the message requests text-to-speech playback.

        Returns:
            The result of this operation.
        """
        route = self._route(
            "POST", "/channels/{channel_id}/messages", channel_id=channel_id
        )
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embed is not None:
            embeds = [embed]
        if embeds is not None:
            normalized = []
            for e in embeds:
                if isinstance(e, Embed):
                    normalized.append(e.to_dict())
                else:
                    normalized.append(e)
            payload["embeds"] = normalized
        if message_reference is not None:
            payload["message_reference"] = _payload_value(message_reference)
        if allowed_mentions is not None:
            payload["allowed_mentions"] = _payload_value(allowed_mentions)
        if flags is not None:
            payload["flags"] = flags
        if nonce is not None:
            payload["nonce"] = nonce
        if favorite_meme_id is not None:
            payload["favorite_meme_id"] = str(favorite_meme_id)
        if sticker_ids is not None:
            payload["sticker_ids"] = [str(sticker_id) for sticker_id in sticker_ids]
        if tts is not None:
            payload["tts"] = tts
        if files:
            return await self.request(route, data=_multipart(payload, files))
        return await self.request(route, json=payload)

    async def get_message(
        self, channel_id: int | str, message_id: int | str
    ) -> dict[str, Any]:
        """GET /channels/{channel_id}/messages/{message_id} - Fetch a single message.

        Args:
            channel_id: Identity of the channel used by this operation.
            message_id: Identity of the message used by this operation.

        Returns:
            The requested message.
        """
        route = self._route(
            "GET",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        return await self.request(route)

    async def get_messages(
        self,
        channel_id: int | str,
        *,
        limit: int = 50,
        before: int | str | None = None,
        after: int | str | None = None,
        around: int | str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /channels/{channel_id}/messages.

        Args:
            channel_id: Identity of the channel used by this operation.
            limit: Maximum entries in the requested page; the route's documented bounds apply.
            before: Exclusive upper cursor for this operation's page.
            after: Exclusive lower message-ID cursor for the requested page.
            around: Message ID around which to centre the requested history page.

        Returns:
            The requested messages.
        """
        if not 1 <= limit <= 100:
            raise ValueError(
                "Message history accepts a single page of 1 to 100 messages"
            )
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        if around:
            params["around"] = around
        route = self._route(
            "GET", "/channels/{channel_id}/messages", channel_id=channel_id
        )
        return await self.request(route, params=params)

    async def edit_message(
        self,
        channel_id: int | str,
        message_id: int | str,
        *,
        content: str | None | UnsetType = UNSET,
        embeds: list[dict[str, Any]] | None = None,
        allowed_mentions: Any | None | UnsetType = UNSET,
        flags: int | None = None,
        attachments: list[dict[str, Any]] | None = None,
        message_snapshots: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """PATCH /channels/{channel_id}/messages/{message_id}.

        Args:
            channel_id: Identity of the channel used by this operation.
            message_id: Identity of the message used by this operation.
            content: Message text. On edits, omission preserves the text and None clears it.
            embeds: Rich embeds in display order; an empty list removes them on an edit.
            allowed_mentions: Mention policy, including explicit empty selections and false flags.
            flags: Bit mask governing the object's documented flags.
            attachments: Attachment metadata; an edit retains only the supplied attachment IDs.
            message_snapshots: Received forward snapshots; snapshots cannot be edited through message mutation.

        Returns:
            The result of this operation.
        """
        route = self._route(
            "PATCH",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        payload: dict[str, Any] = {}
        if not isinstance(content, UnsetType):
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds
        if not isinstance(allowed_mentions, UnsetType):
            payload["allowed_mentions"] = _payload_value(allowed_mentions)
        if flags is not None:
            payload["flags"] = flags
        if attachments is not None:
            payload["attachments"] = attachments
        if message_snapshots is not None:
            raise ValueError("Message snapshots are immutable")
        return await self.request(route, json=payload)

    async def delete_message(
        self, channel_id: int | str, message_id: int | str
    ) -> None:
        """DELETE /channels/{channel_id}/messages/{message_id}.

        Args:
            channel_id: Identity of the channel used by this operation.
            message_id: Identity of the message used by this operation.

        Returns:
            None.
        """
        route = self._route(
            "DELETE",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        await self.request(route)

    async def delete_messages(
        self, channel_id: int | str, message_ids: list[int | str]
    ) -> None:
        """POST /channels/{channel_id}/messages/bulk-delete.

        Args:
            channel_id: Identity of the channel used by this operation.
            message_ids: Between 1 and 100 message IDs from one guild channel; no age limit applies.

        Returns:
            None.
        """
        if not 1 <= len(message_ids) <= 100:
            raise ValueError("Bulk deletion requires between 1 and 100 message IDs")
        route = self._route(
            "POST", "/channels/{channel_id}/messages/bulk-delete", channel_id=channel_id
        )
        payload = {"message_ids": [str(mid) for mid in message_ids]}
        await self.request(route, json=payload)

    async def search_messages(
        self,
        *,
        scope: SearchScope | None = None,
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
    ) -> dict[str, Any]:
        """POST /search/messages - Search indexed Fluxer messages.

        User-token clients may use every documented scope. Bot tokens are
        restricted to `current`, and `current` searches must provide a guild
        or channel context. Prefer `Client.search_messages`,
        `Guild.search_messages`, or `Channel.search_messages` for bot searches.
        Pagination uses `page`; the API accepts but does not honour `cursor`.

        Raises:
            ValueError: A bot requested a non-current scope, or a current-scope
                search has no guild or channel context.

        Args:
            scope: Documented search scope; bot credentials support current context only.
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
        resolved_scope = scope or "current"
        if self.is_bot and resolved_scope != "current":
            raise ValueError("Bot message searches only support scope='current'")
        if (
            resolved_scope == "current"
            and context_channel_id is None
            and (context_guild_id is None)
        ):
            raise ValueError(
                "scope='current' requires context_channel_id or context_guild_id"
            )
        payload: dict[str, Any] = {}
        values = {
            "scope": scope,
            "hits_per_page": hits_per_page,
            "page": page,
            "cursor": cursor,
            "content": content,
            "contents": contents,
            "exact_phrases": exact_phrases,
            "author_type": author_type,
            "exclude_author_type": exclude_author_type,
            "mention_everyone": mention_everyone,
            "pinned": pinned,
            "has": has,
            "exclude_has": exclude_has,
            "embed_type": embed_type,
            "exclude_embed_type": exclude_embed_type,
            "embed_provider": embed_provider,
            "exclude_embed_provider": exclude_embed_provider,
            "link_hostname": link_hostname,
            "exclude_link_hostname": exclude_link_hostname,
            "attachment_filename": attachment_filename,
            "exclude_attachment_filename": exclude_attachment_filename,
            "attachment_extension": attachment_extension,
            "exclude_attachment_extension": exclude_attachment_extension,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "include_nsfw": include_nsfw,
        }
        payload.update(
            {key: value for key, value in values.items() if value is not None}
        )
        scalar_ids = {
            "context_channel_id": context_channel_id,
            "context_guild_id": context_guild_id,
            "min_id": min_id,
            "max_id": max_id,
        }
        payload.update(
            {key: str(value) for key, value in scalar_ids.items() if value is not None}
        )
        list_ids = {
            "channel_ids": channel_ids,
            "channel_id": channel_id,
            "exclude_channel_id": exclude_channel_id,
            "author_id": author_id,
            "exclude_author_id": exclude_author_id,
            "mentions": mentions,
            "exclude_mentions": exclude_mentions,
        }
        payload.update(
            {
                key: [str(item) for item in value]
                for key, value in list_ids.items()
                if value is not None
            }
        )
        return await self.request(self._route("POST", "/search/messages"), json=payload)

    async def get_pinned_messages(
        self,
        channel_id: int | str,
        *,
        limit: int | None = None,
        before: str | None = None,
    ) -> PinPage:
        """GET /channels/{channel_id}/pins - Get all pinned messages in a channel.

        Args:
            channel_id: The channel ID to get pinned messages from.
            limit: Maximum entries in the requested page; the route's documented bounds apply.
            before: ISO8601 pin timestamp bounding this single page.

        Returns:
            List of pinned message objects.
        """
        route = self._route(
            "GET", "/channels/{channel_id}/messages/pins", channel_id=channel_id
        )
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if before is not None:
            params["before"] = before
        return await self.request(route, params=params or None)

    async def pin_message(self, channel_id: int | str, message_id: int | str) -> None:
        """PUT /channels/{channel_id}/pins/{message_id} - Pin a message.

        Args:
            channel_id: The channel ID containing the message.
            message_id: The message ID to pin.

        Returns:
            None (204 No Content)
        """
        route = self._route(
            "PUT",
            "/channels/{channel_id}/pins/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        await self.request(route)

    async def unpin_message(self, channel_id: int | str, message_id: int | str) -> None:
        """DELETE /channels/{channel_id}/pins/{message_id} - Unpin a message.

        Args:
            channel_id: The channel ID containing the message.
            message_id: The message ID to unpin.

        Returns:
            None (204 No Content)
        """
        route = self._route(
            "DELETE",
            "/channels/{channel_id}/pins/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        await self.request(route)

    async def ack_message(self, channel_id: int | str, message_id: int | str) -> None:
        """POST /channels/{channel_id}/messages/{message_id}/ack.

        Args:
            channel_id: Identity of the channel used by this operation.
            message_id: Identity of the message used by this operation.

        Returns:
            None.
        """
        route = self._route(
            "POST",
            "/channels/{channel_id}/messages/{message_id}/ack",
            channel_id=channel_id,
            message_id=message_id,
        )
        await self.request(route, json={})

    async def ack_pins(self, channel_id: int | str) -> None:
        """POST /channels/{channel_id}/pins/ack.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            None.
        """
        route = self._route(
            "POST", "/channels/{channel_id}/pins/ack", channel_id=channel_id
        )
        await self.request(route, json={})

    async def acknowledge_message(
        self, channel_id: int | str, message_id: int | str
    ) -> None:
        """Alias for acknowledging a Fluxer message.

        Args:
            channel_id: Identity of the channel used by this operation.
            message_id: Identity of the message used by this operation.

        Returns:
            None.
        """
        await self.ack_message(channel_id, message_id)

    async def acknowledge_pins(self, channel_id: int | str) -> None:
        """Alias for acknowledging a channel's pin state.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            None.
        """
        await self.ack_pins(channel_id)

    async def get_guild(self, guild_id: int | str) -> dict[str, Any]:
        """GET /guilds/{guild_id}.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}", guild_id=guild_id)
        )

    async def get_guild_channels(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/channels.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild channels.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/channels", guild_id=guild_id)
        )

    async def get_guild_invites(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/invites.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild invites.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/invites", guild_id=guild_id)
        )

    async def get_guild_audit_logs(
        self, guild_id: int | str, **params: Any
    ) -> dict[str, Any]:
        """GET /guilds/{guild_id}/audit-logs.

        Args:
            guild_id: Identity of the guild used by this operation.
            **params: Path, query, or command parameter values used by this operation.

        Returns:
            The requested guild audit logs.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/audit-logs", guild_id=guild_id),
            params=params or None,
        )

    async def get_guild_member(
        self, guild_id: int | str, user_id: int | str
    ) -> dict[str, Any]:
        """GET /guilds/{guild_id}/members/{user_id} — Get a specific guild member.

        Args:
            guild_id: Identity of the guild used by this operation.
            user_id: Identity of the user used by this operation.

        Returns:
            The requested guild member.
        """
        return await self.request(
            self._route(
                "GET",
                "/guilds/{guild_id}/members/{user_id}",
                guild_id=guild_id,
                user_id=user_id,
            )
        )

    async def get_guild_members(
        self, guild_id: int | str, *, limit: int = 100, after: int | str | None = None
    ) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/members — List guild members.

        Args:
            guild_id: Identity of the guild used by this operation.
            limit: Maximum entries in the requested page; the route's documented bounds apply.
            after: Exclusive lower message-ID cursor for the requested page.

        Returns:
            The requested guild members.
        """
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/members", guild_id=guild_id),
            params=params,
        )

    async def create_guild(
        self, *, name: str, icon: bytes | None = None
    ) -> dict[str, Any]:
        """POST /guilds — Create a new guild.

        Args:
            name: Guild name (2-100 characters)
            icon: Icon image data (PNG/JPG/GIF)

        Returns:
            Guild object
        """
        import base64

        payload: dict[str, Any] = {"name": name}
        if icon:
            image_data = base64.b64encode(icon).decode("ascii")
            if icon.startswith(b"\x89PNG"):
                mime_type = "image/png"
            elif icon.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            elif icon.startswith(b"GIF89a") or icon.startswith(b"GIF87a"):
                mime_type = "image/gif"
            else:
                mime_type = "image/png"
            payload["icon"] = f"data:{mime_type};base64,{image_data}"
        return await self.request(self._route("POST", "/guilds"), json=payload)

    async def delete_guild(self, guild_id: int | str, **proof: Any) -> None:
        """Delete an owned guild with caller-supplied sudo verification.

        Args:
            guild_id: Identity of the guild used by this operation.
            **proof: Sudo verification fields accepted by the guild deletion operation.

        Returns:
            None.
        """
        await self.request(
            self._route("POST", "/guilds/{guild_id}/delete", guild_id=guild_id),
            json=proof,
        )

    async def modify_guild(
        self,
        guild_id: int | str,
        *,
        name: str | None = None,
        icon: bytes | None | UnsetType = UNSET,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /guilds/{guild_id} — Modify guild settings.

        Args:
            guild_id: Identity of the guild used by this operation.
            name: Name to assign or resolve in this operation.
            icon: Replacement guild icon; omission preserves it and None clears it.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        import base64

        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if not isinstance(icon, UnsetType):
            if icon is None:
                payload["icon"] = None
            else:
                image_data = base64.b64encode(icon).decode("ascii")
                if icon.startswith(b"\x89PNG"):
                    mime_type = "image/png"
                elif icon.startswith(b"\xff\xd8\xff"):
                    mime_type = "image/jpeg"
                else:
                    mime_type = "image/png"
                payload["icon"] = f"data:{mime_type};base64,{image_data}"
        payload.update(kwargs)
        return await self.request(
            self._route("PATCH", "/guilds/{guild_id}", guild_id=guild_id), json=payload
        )

    async def get_guild_roles(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/roles.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild roles.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/roles", guild_id=guild_id)
        )

    async def create_guild_role(
        self,
        guild_id: int | str,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int = 0,
        hoist: bool = False,
        mentionable: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/roles — Create a new role.

        Args:
            guild_id: Identity of the guild used by this operation.
            name: Name to assign or resolve in this operation.
            permissions: Complete permission bit mask for the requested role operation.
            color: Packed RGB colour value.
            hoist: Whether the role is displayed separately in member lists.
            mentionable: Whether members may mention this role.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        payload: dict[str, Any] = {
            "color": color,
            "name": name if name is not None else "new role",
        }
        if name is not None:
            payload["name"] = name
        if permissions is not None:
            payload["permissions"] = str(permissions)
        payload.update(kwargs)
        result = await self.request(
            self._route("POST", "/guilds/{guild_id}/roles", guild_id=guild_id),
            json=payload,
            headers={"X-Fluxer-Features": "view_channel_members_permission"},
        )
        if hoist or mentionable:
            result = await self.modify_guild_role(
                guild_id, result["id"], hoist=hoist, mentionable=mentionable
            )
        return result

    async def modify_guild_role(
        self,
        guild_id: int | str,
        role_id: int | str,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int | None = None,
        hoist: bool | None = None,
        mentionable: bool | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /guilds/{guild_id}/roles/{role_id}.

        Args:
            guild_id: Identity of the guild used by this operation.
            role_id: Identity of the role used by this operation.
            name: Name to assign or resolve in this operation.
            permissions: Complete permission bit mask for the requested role operation.
            color: Packed RGB colour value.
            hoist: Whether the role is displayed separately in member lists.
            mentionable: Whether members may mention this role.
            reason: Audit-log reason forwarded when the underlying operation supports it.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if permissions is not None:
            payload["permissions"] = str(permissions)
        if color is not None:
            payload["color"] = color
        if hoist is not None:
            payload["hoist"] = hoist
        if mentionable is not None:
            payload["mentionable"] = mentionable
        payload.update(kwargs)
        return await self.request(
            self._route(
                "PATCH",
                "/guilds/{guild_id}/roles/{role_id}",
                guild_id=guild_id,
                role_id=role_id,
            ),
            json=payload,
            reason=reason,
            headers={"X-Fluxer-Features": "view_channel_members_permission"},
        )

    async def delete_guild_role(
        self, guild_id: int | str, role_id: int | str, *, reason: str | None = None
    ) -> None:
        """DELETE /guilds/{guild_id}/roles/{role_id}.

        Args:
            guild_id: Identity of the guild used by this operation.
            role_id: Identity of the role used by this operation.
            reason: Audit-log reason forwarded when the underlying operation supports it.

        Returns:
            None.
        """
        await self.request(
            self._route(
                "DELETE",
                "/guilds/{guild_id}/roles/{role_id}",
                guild_id=guild_id,
                role_id=role_id,
            ),
            reason=reason,
        )

    async def add_guild_member_role(
        self,
        guild_id: int | str,
        user_id: int | str,
        role_id: int | str,
        *,
        reason: str | None = None,
    ) -> None:
        """PUT /guilds/{guild_id}/members/{user_id}/roles/{role_id} — Add a role to a member.

        Args:
            guild_id: Guild ID
            user_id: User/Member ID
            role_id: Role ID to add
            reason: Reason for audit log

        Returns:
            None (204 No Content)
        """
        await self.request(
            self._route(
                "PUT",
                "/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
                guild_id=guild_id,
                user_id=user_id,
                role_id=role_id,
            ),
            reason=reason,
        )

    async def remove_guild_member_role(
        self,
        guild_id: int | str,
        user_id: int | str,
        role_id: int | str,
        *,
        reason: str | None = None,
    ) -> None:
        """DELETE /guilds/{guild_id}/members/{user_id}/roles/{role_id} — Remove a role from a member.

        Args:
            guild_id: Guild ID
            user_id: User/Member ID
            role_id: Role ID to remove
            reason: Reason for audit log

        Returns:
            None (204 No Content)
        """
        await self.request(
            self._route(
                "DELETE",
                "/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
                guild_id=guild_id,
                user_id=user_id,
                role_id=role_id,
            ),
            reason=reason,
        )

    async def kick_guild_member(
        self, guild_id: int | str, user_id: int | str, *, reason: str | None = None
    ) -> None:
        """DELETE /guilds/{guild_id}/members/{user_id} — Remove (kick) a member from a guild.

        Args:
            guild_id: Guild ID
            user_id: User/Member ID to kick
            reason: Reason for audit log

        Returns:
            None (204 No Content)
        """
        await self.request(
            self._route(
                "DELETE",
                "/guilds/{guild_id}/members/{user_id}",
                guild_id=guild_id,
                user_id=user_id,
            ),
            reason=reason,
        )

    async def ban_guild_member(
        self,
        guild_id: int | str,
        user_id: int | str,
        *,
        ban_duration_seconds: int = 0,
        delete_message_days: int = 0,
        delete_message_seconds: int = 0,
        reason: str | None = None,
    ) -> None:
        """PUT /guilds/{guild_id}/bans/{user_id} — Ban a member from a guild.

        Args:
            guild_id: Guild ID
            user_id: User/Member ID to ban
            ban_duration_seconds: Duration of the ban in seconds (0 for permanent, or a valid temporary duration)
            delete_message_days: Number of days to delete messages for (0-7, deprecated)
            delete_message_seconds: Number of seconds to delete messages for (0-604800)
            reason: Reason for audit log

        Returns:
            None (204 No Content)
        """
        payload: dict[str, Any] = {}
        if ban_duration_seconds > 0:
            payload["ban_duration_seconds"] = ban_duration_seconds
        if delete_message_days > 0:
            payload["delete_message_days"] = delete_message_days
        if delete_message_seconds > 0:
            payload["delete_message_seconds"] = delete_message_seconds
        await self.request(
            self._route(
                "PUT",
                "/guilds/{guild_id}/bans/{user_id}",
                guild_id=guild_id,
                user_id=user_id,
            ),
            json=payload if payload else None,
            reason=reason,
        )

    async def unban_guild_member(
        self, guild_id: int | str, user_id: int | str, *, reason: str | None = None
    ) -> None:
        """DELETE /guilds/{guild_id}/bans/{user_id} — Unban a user from a guild.

        Args:
            guild_id: Guild ID
            user_id: User ID to unban
            reason: Reason for audit log

        Returns:
            None (204 No Content)
        """
        await self.request(
            self._route(
                "DELETE",
                "/guilds/{guild_id}/bans/{user_id}",
                guild_id=guild_id,
                user_id=user_id,
            ),
            reason=reason,
        )

    async def timeout_guild_member(
        self,
        guild_id: int | str,
        user_id: int | str,
        *,
        until: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """PATCH /guilds/{guild_id}/members/{user_id} — Timeout (or remove timeout from) a member.

        Args:
            guild_id: Guild ID
            user_id: User/Member ID to timeout
            until: ISO 8601 timestamp for when timeout expires (None to remove timeout)
            reason: Reason for audit log

        Returns:
            Updated member object
        """
        payload: dict[str, Any] = {"communication_disabled_until": until}
        return await self.request(
            self._route(
                "PATCH",
                "/guilds/{guild_id}/members/{user_id}",
                guild_id=guild_id,
                user_id=user_id,
            ),
            json=payload,
            reason=reason,
        )

    async def modify_guild_member(
        self,
        guild_id: int | str,
        user_id: int | str,
        *,
        nick: str | None | UnsetType = UNSET,
        roles: list[int | str] | None = None,
        mute: bool | None = None,
        deaf: bool | None = None,
        channel_id: int | str | None | UnsetType = UNSET,
        communication_disabled_until: str | None | UnsetType = UNSET,
        reason: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /guilds/{guild_id}/members/{user_id} — Modify a guild member.

        Args:
            guild_id: Guild ID
            user_id: User/Member ID to modify
            nick: New nickname (None to remove)
            roles: List of role IDs to set (replaces all roles)
            mute: Whether to mute in voice channels
            deaf: Whether to deafen in voice channels
            channel_id: Voice channel to move member to
            communication_disabled_until: Timeout timestamp (ISO 8601)
            reason: Reason for audit log
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            Updated member object
        """
        payload: dict[str, Any] = {}
        if not isinstance(nick, UnsetType):
            payload["nick"] = nick
        if roles is not None:
            payload["roles"] = [str(r) for r in roles]
        if mute is not None:
            payload["mute"] = mute
        if deaf is not None:
            payload["deaf"] = deaf
        if not isinstance(channel_id, UnsetType):
            payload["channel_id"] = str(channel_id) if channel_id is not None else None
        if not isinstance(communication_disabled_until, UnsetType):
            payload["communication_disabled_until"] = communication_disabled_until
        payload.update(kwargs)
        return await self.request(
            self._route(
                "PATCH",
                "/guilds/{guild_id}/members/{user_id}",
                guild_id=guild_id,
                user_id=user_id,
            ),
            json=payload,
            reason=reason,
        )

    async def create_guild_channel(
        self,
        guild_id: int | str,
        *,
        name: str,
        type: int = 0,
        topic: str | None = None,
        bitrate: int | None = None,
        user_limit: int | None = None,
        position: int | None = None,
        parent_id: int | str | None = None,
        nsfw: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/channels — Create a channel.

        Args:
            guild_id: Guild to create channel in
            name: Channel name
            type: Guild channel variant: 0 text, 2 voice, 4 category, or 998 link.
            topic: Channel topic (text channels)
            bitrate: Bitrate (voice channels)
            user_limit: User limit (voice channels)
            position: Unsupported compatibility argument; use the existing bulk reposition operation.
            parent_id: Parent category ID
            nsfw: Whether the channel is NSFW
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            Channel object
        """
        if type not in (0, 2, 4, 998):
            raise ValueError("Guild channel type must be 0, 2, 4, or 998")
        if type == 4 and parent_id is not None:
            raise ValueError("A category cannot have a parent")
        payload: dict[str, Any] = {"name": name, "type": type, "nsfw": nsfw}
        if topic is not None:
            payload["topic"] = topic
        if bitrate is not None:
            payload["bitrate"] = bitrate
        if user_limit is not None:
            payload["user_limit"] = user_limit
        if position is not None:
            raise ValueError(
                "The position field is not supported by this channel operation"
            )
        if parent_id is not None:
            payload["parent_id"] = str(parent_id)
        payload.update(kwargs)
        return await self.request(
            self._route("POST", "/guilds/{guild_id}/channels", guild_id=guild_id),
            json=payload,
            headers={"X-Fluxer-Features": "view_channel_members_permission"},
        )

    async def modify_channel(
        self,
        channel_id: int | str,
        *,
        name: str | None | UnsetType = UNSET,
        type: int | None = None,
        topic: str | None | UnsetType = UNSET,
        position: int | None = None,
        parent_id: int | str | None | UnsetType = UNSET,
        nsfw: bool | None | UnsetType = UNSET,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /channels/{channel_id}.

        Args:
            channel_id: Identity of the channel used by this operation.
            name: Name to assign or resolve in this operation.
            type: Type used by this operation.
            topic: Topic used by this operation.
            position: Position used by this operation.
            parent_id: Identity of the parent used by this operation.
            nsfw: Nsfw used by this operation.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        payload: dict[str, Any] = {}
        if not isinstance(name, UnsetType):
            payload["name"] = name
        if type is not None:
            raise ValueError(
                "The type field is not supported by this channel operation"
            )
        if not isinstance(topic, UnsetType):
            payload["topic"] = topic
        if position is not None:
            raise ValueError(
                "The position field is not supported by this channel operation"
            )
        if not isinstance(parent_id, UnsetType):
            payload["parent_id"] = str(parent_id) if parent_id is not None else None
        if not isinstance(nsfw, UnsetType):
            payload["nsfw"] = nsfw
        payload.update(kwargs)
        return await self.request(
            self._route("PATCH", "/channels/{channel_id}", channel_id=channel_id),
            json=payload,
            headers={"X-Fluxer-Features": "view_channel_members_permission"},
        )

    async def delete_channel(self, channel_id: int | str) -> None:
        """DELETE /channels/{channel_id}.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            None.
        """
        await self.request(
            self._route("DELETE", "/channels/{channel_id}", channel_id=channel_id)
        )

    async def edit_channel_permissions(
        self,
        channel_id: int | str,
        overwrite_id: int | str,
        *,
        allow: int | str | None | UnsetType = UNSET,
        deny: int | str | None | UnsetType = UNSET,
        type: int = 0,
        **kwargs: Any,
    ) -> None:
        """PUT /channels/{channel_id}/permissions/{overwrite_id} — Edit channel permission overwrites.

        Args:
            channel_id: Channel ID
            overwrite_id: Role or user ID
            allow: Allowed permissions (bitwise)
            deny: Denied permissions (bitwise)
            type: 0 for role, 1 for member
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            None (204 No Content)
        """
        payload: dict[str, Any] = {"type": type}
        if not isinstance(allow, UnsetType):
            payload["allow"] = str(allow) if allow is not None else None
        if not isinstance(deny, UnsetType):
            payload["deny"] = str(deny) if deny is not None else None
        payload.update(kwargs)
        await self.request(
            self._route(
                "PUT",
                "/channels/{channel_id}/permissions/{overwrite_id}",
                channel_id=channel_id,
                overwrite_id=overwrite_id,
            ),
            json=payload,
            headers={"X-Fluxer-Features": "view_channel_members_permission"},
        )

    async def modify_current_user(
        self,
        *,
        username: str | None = None,
        avatar: bytes | None | UnsetType = UNSET,
        banner: bytes | None | UnsetType = UNSET,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /users/@me — Modify the current user's profile.

        Args:
            username: New username
            avatar: Avatar image data (PNG/JPG/GIF)
            banner: Banner image data (PNG/JPG/GIF)
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            Updated user object
        """
        import base64

        payload: dict[str, Any] = {}
        if username is not None:
            payload["username"] = username
        if not isinstance(avatar, UnsetType):
            if avatar is None:
                payload["avatar"] = None
            else:
                image_data = base64.b64encode(avatar).decode("ascii")
                if avatar.startswith(b"\x89PNG"):
                    mime_type = "image/png"
                elif avatar.startswith(b"\xff\xd8\xff"):
                    mime_type = "image/jpeg"
                elif avatar.startswith(b"GIF89a") or avatar.startswith(b"GIF87a"):
                    mime_type = "image/gif"
                else:
                    mime_type = "image/png"
                payload["avatar"] = f"data:{mime_type};base64,{image_data}"
        if not isinstance(banner, UnsetType):
            if banner is None:
                payload["banner"] = None
            else:
                image_data = base64.b64encode(banner).decode("ascii")
                if banner.startswith(b"\x89PNG"):
                    mime_type = "image/png"
                elif banner.startswith(b"\xff\xd8\xff"):
                    mime_type = "image/jpeg"
                elif banner.startswith(b"GIF89a") or banner.startswith(b"GIF87a"):
                    mime_type = "image/gif"
                else:
                    mime_type = "image/png"
                payload["banner"] = f"data:{mime_type};base64,{image_data}"
        payload.update(kwargs)
        return await self.request(self._route("PATCH", "/users/@me"), json=payload)

    async def get_guild_emojis(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/emojis — Get all emojis for a guild.

        Returns:
            List of emoji objects

        Args:
            guild_id: Identity of the guild used by this operation.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/emojis", guild_id=guild_id)
        )

    async def get_guild_emoji(
        self, guild_id: int | str, emoji_id: int | str
    ) -> dict[str, Any]:
        """Select an expression from the documented guild list.

        Args:
            guild_id: Identity of the guild used by this operation.
            emoji_id: Identity of the emoji used by this operation.

        Returns:
            The requested guild emoji.
        """
        for item in await self.get_guild_emojis(guild_id):
            if str(item["id"]) == str(emoji_id):
                return item
        raise NotFound(404, "UNKNOWN_EMOJI", "Expression not found in guild")

    async def create_guild_emoji(
        self,
        guild_id: int | str,
        *,
        name: str,
        image: bytes,
        roles: list[int | str] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/emojis — Create a new emoji.

        Args:
            guild_id: Guild ID
            name: Emoji name
            image: Image data (PNG/JPG/GIF)
            roles: Compatibility argument; nonempty role restrictions are unsupported and rejected.
            reason: Reason for creation (audit log)

        Returns:
            Emoji object
        """
        import base64

        image_data = base64.b64encode(image).decode("ascii")
        if image.startswith(b"\x89PNG"):
            mime_type = "image/png"
        elif image.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif image.startswith(b"GIF89a") or image.startswith(b"GIF87a"):
            mime_type = "image/gif"
        else:
            mime_type = "image/png"
        payload: dict[str, Any] = {
            "name": name,
            "image": f"data:{mime_type};base64,{image_data}",
        }
        if roles:
            raise ValueError("Fluxer does not support expression role restrictions")
        return await self.request(
            self._route("POST", "/guilds/{guild_id}/emojis", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    async def delete_guild_emoji(
        self, guild_id: int | str, emoji_id: int | str, *, reason: str | None = None
    ) -> None:
        """DELETE /guilds/{guild_id}/emojis/{emoji_id} — Delete an emoji.

        Args:
            guild_id: Guild ID
            emoji_id: Emoji ID
            reason: Reason for deletion (audit log)

        Returns:
            None.
        """
        await self.request(
            self._route(
                "DELETE",
                "/guilds/{guild_id}/emojis/{emoji_id}",
                guild_id=guild_id,
                emoji_id=emoji_id,
            ),
            reason=reason,
        )

    async def get_guild_stickers(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/stickers — Get all stickers for a guild.

        Returns:
            List of emoji objects

        Args:
            guild_id: Identity of the guild used by this operation.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/stickers", guild_id=guild_id)
        )

    async def get_guild_sticker(
        self, guild_id: int | str, sticker_id: int | str
    ) -> dict[str, Any]:
        """Select an expression from the documented guild list.

        Args:
            guild_id: Identity of the guild used by this operation.
            sticker_id: Identity of the sticker used by this operation.

        Returns:
            The requested guild sticker.
        """
        for item in await self.get_guild_stickers(guild_id):
            if str(item["id"]) == str(sticker_id):
                return item
        raise NotFound(404, "UNKNOWN_STICKER", "Expression not found in guild")

    async def create_guild_sticker(
        self,
        guild_id: int | str,
        *,
        name: str,
        image: bytes,
        roles: list[int | str] | None = None,
        reason: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/stickers — Create a new sticker.

        Args:
            guild_id: Guild ID
            name: Sticker name
            image: Image data (PNG/JPG/GIF)
            roles: Compatibility argument; nonempty role restrictions are unsupported and rejected.
            reason: Reason for creation (audit log)
            description: Descriptive text associated with this object.
            tags: Tags used by this operation.

        Returns:
            Sticker object
        """
        import base64

        image_data = base64.b64encode(image).decode("ascii")
        if image.startswith(b"\x89PNG"):
            mime_type = "image/png"
        elif image.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif image.startswith(b"GIF89a") or image.startswith(b"GIF87a"):
            mime_type = "image/gif"
        else:
            mime_type = "image/png"
        payload: dict[str, Any] = {
            "name": name,
            "image": f"data:{mime_type};base64,{image_data}",
        }
        if roles:
            raise ValueError("Fluxer does not support expression role restrictions")
        payload["description"] = description
        payload["tags"] = tags or []
        return await self.request(
            self._route("POST", "/guilds/{guild_id}/stickers", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    async def delete_guild_sticker(
        self, guild_id: int | str, sticker_id: int | str, *, reason: str | None = None
    ) -> None:
        """DELETE /guilds/{guild_id}/stickers/{sticker_id} — Delete an sticker.

        Args:
            guild_id: Guild ID
            sticker_id: Sticker ID
            reason: Reason for deletion (audit log)

        Returns:
            None.
        """
        await self.request(
            self._route(
                "DELETE",
                "/guilds/{guild_id}/stickers/{sticker_id}",
                guild_id=guild_id,
                sticker_id=sticker_id,
            ),
            reason=reason,
        )

    async def get_guild_discovery_status(self, guild_id: int | str) -> dict[str, Any]:
        """GET /guilds/{guild_id}/discovery.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild discovery status.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/discovery", guild_id=guild_id)
        )

    async def apply_for_guild_discovery(
        self, guild_id: int | str, **payload: Any
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/discovery.

        Args:
            guild_id: Identity of the guild used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route("POST", "/guilds/{guild_id}/discovery", guild_id=guild_id),
            json=payload,
        )

    async def edit_guild_discovery_application(
        self, guild_id: int | str, **payload: Any
    ) -> dict[str, Any]:
        """PATCH /guilds/{guild_id}/discovery.

        Args:
            guild_id: Identity of the guild used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route("PATCH", "/guilds/{guild_id}/discovery", guild_id=guild_id),
            json=payload,
        )

    async def apply_for_discovery(
        self, guild_id: int | str, **payload: Any
    ) -> dict[str, Any]:
        """Alias for applying a guild to Fluxer discovery.

        Args:
            guild_id: Identity of the guild used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        return await self.apply_for_guild_discovery(guild_id, **payload)

    async def edit_discovery_application(
        self, guild_id: int | str, **payload: Any
    ) -> dict[str, Any]:
        """Alias for editing a guild discovery application.

        Args:
            guild_id: Identity of the guild used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        return await self.edit_guild_discovery_application(guild_id, **payload)

    async def withdraw_discovery_application(self, guild_id: int | str) -> None:
        """DELETE /guilds/{guild_id}/discovery.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            None.
        """
        await self.request(
            self._route("DELETE", "/guilds/{guild_id}/discovery", guild_id=guild_id)
        )

    async def join_discovery_guild(self, guild_id: int | str) -> None:
        """POST /discovery/guilds/{guild_id}/join.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route("POST", "/discovery/guilds/{guild_id}/join", guild_id=guild_id)
        )

    async def get_guild_vanity_url(self, guild_id: int | str) -> dict[str, Any]:
        """GET /guilds/{guild_id}/vanity-url.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild vanity url.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/vanity-url", guild_id=guild_id)
        )

    async def update_guild_vanity_url(
        self, guild_id: int | str, code: str
    ) -> dict[str, Any]:
        """PATCH /guilds/{guild_id}/vanity-url.

        Args:
            guild_id: Identity of the guild used by this operation.
            code: Stable server error code or invite identifier for this operation.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route("PATCH", "/guilds/{guild_id}/vanity-url", guild_id=guild_id),
            json={"code": code},
        )

    async def transfer_guild_ownership(
        self, guild_id: int | str, new_owner_id: int | str, **payload: Any
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/transfer-ownership.

        Args:
            guild_id: Identity of the guild used by this operation.
            new_owner_id: Identity of the new owner used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        payload["new_owner_id"] = str(new_owner_id)
        return await self.request(
            self._route(
                "POST", "/guilds/{guild_id}/transfer-ownership", guild_id=guild_id
            ),
            json=payload,
        )

    async def bulk_create_guild_emojis(
        self, guild_id: int | str, emojis: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/emojis/bulk.

        Args:
            guild_id: Identity of the guild used by this operation.
            emojis: Emojis used by this operation.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route("POST", "/guilds/{guild_id}/emojis/bulk", guild_id=guild_id),
            json={"emojis": emojis},
        )

    async def bulk_create_guild_stickers(
        self, guild_id: int | str, stickers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/stickers/bulk.

        Args:
            guild_id: Identity of the guild used by this operation.
            stickers: Stickers used by this operation.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route("POST", "/guilds/{guild_id}/stickers/bulk", guild_id=guild_id),
            json={"stickers": stickers},
        )

    async def clone_guild_emoji(
        self, guild_id: int | str, **payload: Any
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/emojis/clone.

        Args:
            guild_id: Identity of the guild used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route("POST", "/guilds/{guild_id}/emojis/clone", guild_id=guild_id),
            json=payload,
        )

    async def clone_guild_sticker(
        self, guild_id: int | str, **payload: Any
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/stickers/clone.

        Args:
            guild_id: Identity of the guild used by this operation.
            **payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route("POST", "/guilds/{guild_id}/stickers/clone", guild_id=guild_id),
            json=payload,
        )

    async def get_guild_webhooks(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/webhooks.

        Args:
            guild_id: Identity of the guild used by this operation.

        Returns:
            The requested guild webhooks.
        """
        return await self.request(
            self._route("GET", "/guilds/{guild_id}/webhooks", guild_id=guild_id)
        )

    async def get_channel_webhooks(self, channel_id: int | str) -> list[dict[str, Any]]:
        """GET /channels/{channel_id}/webhooks.

        Args:
            channel_id: Identity of the channel used by this operation.

        Returns:
            The requested channel webhooks.
        """
        return await self.request(
            self._route("GET", "/channels/{channel_id}/webhooks", channel_id=channel_id)
        )

    async def create_webhook(
        self, channel_id: int | str, *, name: str, avatar: str | None = None
    ) -> dict[str, Any]:
        """POST /channels/{channel_id}/webhooks.

        Args:
            channel_id: Identity of the channel used by this operation.
            name: Name to assign or resolve in this operation.
            avatar: Replacement avatar; on an edit, omission preserves it and None clears it.

        Returns:
            The result of this operation.
        """
        payload: dict[str, Any] = {"name": name}
        if avatar is not None:
            payload["avatar"] = avatar
        return await self.request(
            self._route(
                "POST", "/channels/{channel_id}/webhooks", channel_id=channel_id
            ),
            json=payload,
        )

    async def get_webhook(self, webhook_id: int | str) -> dict[str, Any]:
        """GET /webhooks/{webhook_id}.

        Args:
            webhook_id: Identity of the webhook used by this operation.

        Returns:
            The requested webhook.
        """
        return await self.request(
            self._route("GET", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        )

    async def get_webhook_with_token(
        self, webhook_id: int | str, token: str
    ) -> dict[str, Any]:
        """GET /webhooks/{webhook_id}/{token}.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.

        Returns:
            The requested webhook with token.
        """
        return await self.request(
            self._route(
                "GET",
                "/webhooks/{webhook_id}/{token}",
                webhook_id=webhook_id,
                token=token,
            )
        )

    async def modify_webhook(
        self,
        webhook_id: int | str,
        *,
        name: str | None = None,
        avatar: str | None | UnsetType = UNSET,
        channel_id: int | str | None = None,
    ) -> dict[str, Any]:
        """PATCH /webhooks/{webhook_id}.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            name: Name to assign or resolve in this operation.
            avatar: Replacement avatar; on an edit, omission preserves it and None clears it.
            channel_id: Identity of the channel used by this operation.

        Returns:
            The result of this operation.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if not isinstance(avatar, UnsetType):
            payload["avatar"] = avatar
        if channel_id is not None:
            payload["channel_id"] = str(channel_id) if channel_id is not None else None
        return await self.request(
            self._route("PATCH", "/webhooks/{webhook_id}", webhook_id=webhook_id),
            json=payload,
        )

    async def modify_webhook_with_token(
        self,
        webhook_id: int | str,
        token: str,
        *,
        name: str | None = None,
        avatar: str | None | UnsetType = UNSET,
        channel_id: int | str | None = None,
    ) -> dict[str, Any]:
        """PATCH /webhooks/{webhook_id}/{token}.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.
            name: Name to assign or resolve in this operation.
            avatar: Replacement avatar; on an edit, omission preserves it and None clears it.
            channel_id: Identity of the channel used by this operation.

        Returns:
            The result of this operation.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if not isinstance(avatar, UnsetType):
            payload["avatar"] = avatar
        if channel_id is not None:
            raise ValueError("Token-only webhooks cannot move channels")
        return await self.request(
            self._route(
                "PATCH",
                "/webhooks/{webhook_id}/{token}",
                webhook_id=webhook_id,
                token=token,
            ),
            json=payload,
        )

    async def delete_webhook(
        self, webhook_id: int | str, *, reason: str | None = None
    ) -> None:
        """DELETE /webhooks/{webhook_id}.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            reason: Audit-log reason forwarded when the underlying operation supports it.

        Returns:
            None.
        """
        await self.request(
            self._route("DELETE", "/webhooks/{webhook_id}", webhook_id=webhook_id),
            reason=reason,
        )

    async def delete_webhook_with_token(
        self, webhook_id: int | str, token: str
    ) -> None:
        """DELETE /webhooks/{webhook_id}/{token}.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.

        Returns:
            None.
        """
        await self.request(
            self._route(
                "DELETE",
                "/webhooks/{webhook_id}/{token}",
                webhook_id=webhook_id,
                token=token,
            )
        )

    async def execute_webhook(
        self,
        webhook_id: int | str,
        token: str,
        *,
        content: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        wait: bool = False,
        files: list[dict[str, Any]] | None = None,
        allowed_mentions: Any | None = None,
        message_reference: Any | None = None,
        flags: int | None = None,
        nonce: str | int | None = None,
        favorite_meme_id: int | str | None = None,
        sticker_ids: list[int | str] | None = None,
        tts: bool | None = None,
    ) -> dict[str, Any] | None:
        """POST /webhooks/{webhook_id}/{token}.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.
            content: Text content sent in the message.
            embeds: Rich embeds in display order; an empty list removes them on an edit.
            username: Username used by this operation.
            avatar_url: Avatar URL override for this webhook message.
            wait: Whether to return the created webhook message instead of an empty response.
            files: Files uploaded with this message in the supplied order.
            allowed_mentions: Mention policy, including explicit empty selections and false flags.
            message_reference: Reply or forward reference and any explicit attachment/embed selections.
            flags: Bit mask governing the object's documented flags.
            nonce: Caller-selected correlation value echoed by the operation when supported.
            favorite_meme_id: Identity of the favorite meme used by this operation.
            sticker_ids: IDs of the sticker resources selected by this operation.
            tts: Whether the message requests text-to-speech playback.

        Returns:
            The result of this operation.
        """
        route = self._route(
            "POST", "/webhooks/{webhook_id}/{token}", webhook_id=webhook_id, token=token
        )
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds
        if username is not None:
            payload["username"] = username
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url
        if allowed_mentions is not None:
            payload["allowed_mentions"] = _payload_value(allowed_mentions)
        if message_reference is not None:
            payload["message_reference"] = _payload_value(message_reference)
        if flags is not None:
            payload["flags"] = flags
        if nonce is not None:
            payload["nonce"] = nonce
        if favorite_meme_id is not None:
            payload["favorite_meme_id"] = str(favorite_meme_id)
        if sticker_ids is not None:
            payload["sticker_ids"] = [str(sticker_id) for sticker_id in sticker_ids]
        if tts is not None:
            payload["tts"] = tts
        params = {"wait": "true"} if wait else None
        if files:
            return await self.request(
                route, data=_multipart(payload, files), params=params
            )
        return await self.request(route, json=payload, params=params)

    async def edit_webhook_message(
        self,
        webhook_id: int | str,
        token: str,
        message_id: int | str,
        *,
        content: str | None | UnsetType = UNSET,
        embeds: list[dict[str, Any]] | None = None,
        allowed_mentions: Any | None | UnsetType = UNSET,
        flags: int | None = None,
    ) -> dict[str, Any]:
        """PATCH /webhooks/{webhook_id}/{token}/messages/{message_id}.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.
            message_id: Identity of the message used by this operation.
            content: Message text. On edits, omission preserves the text and None clears it.
            embeds: Rich embeds in display order; an empty list removes them on an edit.
            allowed_mentions: Mention policy, including explicit empty selections and false flags.
            flags: Bit mask governing the object's documented flags.

        Returns:
            The result of this operation.
        """
        route = self._route(
            "PATCH",
            "/webhooks/{webhook_id}/{token}/messages/{message_id}",
            webhook_id=webhook_id,
            token=token,
            message_id=message_id,
        )
        payload: dict[str, Any] = {}
        if not isinstance(content, UnsetType):
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds
        if not isinstance(allowed_mentions, UnsetType):
            payload["allowed_mentions"] = _payload_value(allowed_mentions)
        if flags is not None:
            payload["flags"] = flags
        return await self.request(route, json=payload)

    async def delete_webhook_message(
        self, webhook_id: int | str, token: str, message_id: int | str
    ) -> None:
        """DELETE /webhooks/{webhook_id}/{token}/messages/{message_id}.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.
            message_id: Identity of the message used by this operation.

        Returns:
            None.
        """
        await self.request(
            self._route(
                "DELETE",
                "/webhooks/{webhook_id}/{token}/messages/{message_id}",
                webhook_id=webhook_id,
                token=token,
                message_id=message_id,
            )
        )

    async def execute_github_webhook(
        self,
        webhook_id: int | str,
        token: str,
        payload: dict[str, Any],
        *,
        event: str | None = None,
        delivery: str | None = None,
    ) -> None:
        """POST /webhooks/{webhook_id}/{token}/github.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.
            payload: Operation-specific fields in the documented request shape.
            event: Event name used for registration or webhook callback headers.
            delivery: GitHub delivery identifier used for callback deduplication.

        Returns:
            None.
        """
        return await self.request(
            self._route(
                "POST",
                "/webhooks/{webhook_id}/{token}/github",
                webhook_id=webhook_id,
                token=token,
            ),
            json=payload,
            headers={
                k: v
                for k, v in {
                    "X-GitHub-Event": event,
                    "X-GitHub-Delivery": delivery,
                }.items()
                if v is not None
            },
        )

    async def execute_instatus_webhook(
        self, webhook_id: int | str, token: str, payload: dict[str, Any]
    ) -> None:
        """POST /webhooks/{webhook_id}/{token}/instatus.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.
            payload: Operation-specific fields in the documented request shape.

        Returns:
            None.
        """
        return await self.request(
            self._route(
                "POST",
                "/webhooks/{webhook_id}/{token}/instatus",
                webhook_id=webhook_id,
                token=token,
            ),
            json=payload,
        )

    async def execute_slack_webhook(
        self, webhook_id: int | str, token: str, payload: dict[str, Any]
    ) -> str:
        """POST /webhooks/{webhook_id}/{token}/slack.

        Args:
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.
            payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        return await self.request(
            self._route(
                "POST",
                "/webhooks/{webhook_id}/{token}/slack",
                webhook_id=webhook_id,
                token=token,
            ),
            json=payload,
        )

    def _emoji_to_url_format(self, emoji: Any) -> str:
        import re
        import emoji as emoji_lib

        if getattr(emoji, "id", None) is not None:
            return f"{emoji.name}:{emoji.id}"
        value = (
            getattr(emoji, "unicode", None)
            or getattr(emoji, "name", None)
            or str(emoji)
        )
        match = re.fullmatch("<a?:([^:]+):(\\d+)>", value)
        if match:
            return f"{match[1]}:{match[2]}"
        return emoji_lib.emojize(value, language="alias")

    async def add_reaction(
        self, channel_id: int | str, message_id: int | str, emoji: Any
    ) -> None:
        """PUT /channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me.

        Add a reaction to a message.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            emoji: Emoji to react with (PartialEmoji, Emoji, or unicode string)

        Returns:
            None.
        """
        emoji_str = self._emoji_to_url_format(emoji)
        await self.request(
            self._route(
                "PUT",
                "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me",
                channel_id=channel_id,
                message_id=message_id,
                emoji=emoji_str,
            )
        )

    async def delete_reaction(
        self,
        channel_id: int | str,
        message_id: int | str,
        emoji: Any,
        user_id: int | str = "@me",
    ) -> None:
        """DELETE /channels/{channel_id}/messages/{message_id}/reactions/{emoji}/{user_id}.

        Remove a reaction from a message.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            emoji: Emoji to remove (PartialEmoji, Emoji, or unicode string)
            user_id: User ID to remove reaction from (default: @me)

        Returns:
            None.
        """
        emoji_str = self._emoji_to_url_format(emoji)
        await self.request(
            self._route(
                "DELETE",
                "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/{user_id}",
                channel_id=channel_id,
                message_id=message_id,
                emoji=emoji_str,
                user_id=user_id,
            )
        )

    async def get_reaction_users(
        self,
        channel_id: int | str,
        message_id: int | str,
        emoji: Any,
        *,
        limit: int = 25,
        after: int | str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /channels/{channel_id}/messages/{message_id}/reactions/{emoji}.

        Get users who reacted with a specific emoji.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            emoji: Emoji to get users for (PartialEmoji, Emoji, or unicode string)
            limit: Max number of users to return (1-100, default 25)
            after: Get users after this user ID

        Returns:
            List of user objects
        """
        emoji_str = self._emoji_to_url_format(emoji)
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        return await self.request(
            self._route(
                "GET",
                "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}",
                channel_id=channel_id,
                message_id=message_id,
                emoji=emoji_str,
            ),
            params=params,
        )

    async def delete_all_reactions(
        self, channel_id: int | str, message_id: int | str
    ) -> None:
        """DELETE /channels/{channel_id}/messages/{message_id}/reactions.

        Remove all reactions from a message.

        Args:
            channel_id: Channel ID
            message_id: Message ID

        Returns:
            None.
        """
        await self.request(
            self._route(
                "DELETE",
                "/channels/{channel_id}/messages/{message_id}/reactions",
                channel_id=channel_id,
                message_id=message_id,
            )
        )

    async def delete_all_reactions_for_emoji(
        self, channel_id: int | str, message_id: int | str, emoji: Any
    ) -> None:
        """DELETE /channels/{channel_id}/messages/{message_id}/reactions/{emoji}.

        Remove all reactions of a specific emoji from a message.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            emoji: Emoji to remove all reactions for (PartialEmoji, Emoji, or unicode string)

        Returns:
            None.
        """
        emoji_str = self._emoji_to_url_format(emoji)
        await self.request(
            self._route(
                "DELETE",
                "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}",
                channel_id=channel_id,
                message_id=message_id,
                emoji=emoji_str,
            )
        )

    async def delete_invite(self, invite_code: str) -> None:
        """Revoke an invite using the authenticated caller's permissions.

        Args:
            invite_code: Invite code used by this operation.

        Returns:
            None.
        """
        await self.request(
            self._route("DELETE", "/invites/{invite_code}", invite_code=invite_code)
        )
