from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from fluxer.models.user import User

if TYPE_CHECKING:
    from ..file import File
    from ..http import HTTPClient


@dataclass(slots=True)
class WebhookMessage:
    """Message created by a Fluxer webhook."""

    id: int
    channel_id: int
    content: str
    author: User
    timestamp: str
    edited_timestamp: str | None = None

    embeds: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[Any] = field(default_factory=list)
    mentions: list[User] = field(default_factory=list)
    pinned: bool = False

    webhook_id: int | None = None
    webhook_token: str | None = None
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        webhook_id: int | str | None = None,
        token: str | None = None,
    ) -> WebhookMessage:
        from .attachment import Attachment

        return cls(
            id=int(data["id"]),
            channel_id=int(data["channel_id"]),
            content=data.get("content", ""),
            author=User.from_data(data["author"], http),
            timestamp=data["timestamp"],
            edited_timestamp=data.get("edited_timestamp"),
            embeds=data.get("embeds", []),
            attachments=[Attachment.from_data(a) for a in data.get("attachments", [])],
            mentions=[User.from_data(u, http) for u in data.get("mentions", [])],
            pinned=data.get("pinned", False),
            webhook_id=int(webhook_id) if webhook_id is not None else None,
            webhook_token=token,
            _http=http,
        )

    async def edit(self, content: str | None = None, **kwargs: Any) -> WebhookMessage:
        if self._http is None or self.webhook_id is None or self.webhook_token is None:
            raise RuntimeError("WebhookMessage is not bound to a webhook HTTP client")
        payload = {key: value for key, value in kwargs.items() if value is not None}
        if content is not None:
            payload["content"] = content
        data = await self._http.edit_webhook_message(
            self.webhook_id,
            self.webhook_token,
            self.id,
            **payload,
        )
        return WebhookMessage.from_data(
            data,
            self._http,
            webhook_id=self.webhook_id,
            token=self.webhook_token,
        )

    async def delete(self) -> None:
        if self._http is None or self.webhook_id is None or self.webhook_token is None:
            raise RuntimeError("WebhookMessage is not bound to a webhook HTTP client")
        await self._http.delete_webhook_message(
            self.webhook_id,
            self.webhook_token,
            self.id,
        )


@dataclass(slots=True)
class Webhook:
    """Represents a Fluxer webhook."""

    id: int
    guild_id: int
    channel_id: int
    user: User
    name: str
    avatar: str | None
    token: str

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_url(cls, url: str, *, http: HTTPClient | None = None) -> Webhook:
        """Create a webhook handle from a Fluxer webhook URL."""
        path = [part for part in urlparse(url).path.split("/") if part]
        try:
            index = path.index("webhooks")
            webhook_id = int(path[index + 1])
            token = path[index + 2]
        except (ValueError, IndexError) as exc:
            raise ValueError("Invalid Fluxer webhook URL") from exc

        return cls(
            id=webhook_id,
            guild_id=0,
            channel_id=0,
            user=User(id=0, username="webhook"),
            name="Webhook",
            avatar=None,
            token=token,
            _http=http,
        )

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        guild_id: int | None = None,
    ) -> Webhook:
        """Construct a Webhook from raw API data.

        Args:
            data: Raw webhook object from the API.
            http: HTTPClient for making further requests.
            guild_id: Override guild_id if not present in data.

        Returns:
            A new Webhook instance.
        """
        return cls(
            id=int(data["id"]),
            guild_id=guild_id or int(data["guild_id"]),
            channel_id=int(data["channel_id"]),
            user=User.from_data(data["user"], http),
            name=data["name"],
            avatar=data.get("avatar", None),
            token=data["token"],
            _http=http,
        )

    async def edit(
        self,
        *,
        name: str | None = None,
        avatar: str | None = None,
        channel_id: int | None = None,
    ) -> Webhook:
        """Edit this webhook.

        Args:
            name: New webhook name.
            avatar: New avatar (base64 data URI).
            channel_id: Move webhook to a different channel.

        Returns:
            The updated Webhook.
        """
        if not self._http:
            raise RuntimeError("Cannot edit webhook without HTTPClient")

        data = await self._http.modify_webhook(
            self.id, name=name, avatar=avatar, channel_id=channel_id
        )
        return Webhook.from_data(data, self._http)

    async def send(
        self,
        content: str | None = None,
        *,
        embeds: list[dict[str, Any]] | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        wait: bool = False,
        allowed_mentions: Any | None = None,
        message_reference: Any | None = None,
        flags: int | None = None,
        nonce: str | int | None = None,
        favorite_meme_id: int | str | None = None,
        sticker_ids: list[int | str] | None = None,
        tts: bool | None = None,
    ) -> WebhookMessage | None:
        """Send a message with this webhook.

        Args:
            content: Text content of the message.
            embeds: List of embed dicts to include.
            username: Override the webhook's default name.
            avatar_url: Override the webhook's default avatar.
            file: A single File object to attach.
            files: Multiple File objects to attach.
            wait: If True, returns the created Message.

        Returns:
            The created Message if wait=True, otherwise None.
        """
        if not self._http:
            raise RuntimeError("Cannot send with webhook without HTTPClient")

        file_list: list[dict[str, Any]] | None = None
        if file is not None:
            file_list = [file.to_dict()]
        elif files is not None:
            file_list = [f.to_dict() for f in files]

        data = await self._http.execute_webhook(
            self.id,
            self.token,
            content=content,
            embeds=embeds,
            username=username,
            avatar_url=avatar_url,
            wait=wait,
            files=file_list,
            allowed_mentions=allowed_mentions,
            message_reference=message_reference,
            flags=flags,
            nonce=nonce,
            favorite_meme_id=favorite_meme_id,
            sticker_ids=sticker_ids,
            tts=tts,
        )
        if data is not None:
            return WebhookMessage.from_data(
                data,
                self._http,
                webhook_id=self.id,
                token=self.token,
            )
        return None

    async def edit_message(
        self,
        message_id: int | str,
        *,
        content: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
        allowed_mentions: Any | None = None,
        flags: int | None = None,
    ) -> WebhookMessage:
        """Edit a message previously created by this webhook."""
        if not self._http:
            raise RuntimeError("Cannot edit webhook message without HTTPClient")
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds
        if allowed_mentions is not None:
            payload["allowed_mentions"] = allowed_mentions
        if flags is not None:
            payload["flags"] = flags

        data = await self._http.edit_webhook_message(
            self.id,
            self.token,
            message_id,
            **payload,
        )
        return WebhookMessage.from_data(
            data,
            self._http,
            webhook_id=self.id,
            token=self.token,
        )

    async def delete_message(self, message_id: int | str) -> None:
        """Delete a message previously created by this webhook."""
        if not self._http:
            raise RuntimeError("Cannot delete webhook message without HTTPClient")
        await self._http.delete_webhook_message(self.id, self.token, message_id)

    async def execute_github(self, payload: dict[str, Any]) -> Any:
        """Execute this webhook with a GitHub-shaped payload."""
        if not self._http:
            raise RuntimeError("Cannot execute webhook without HTTPClient")
        return await self._http.execute_github_webhook(self.id, self.token, payload)

    async def execute_instatus(self, payload: dict[str, Any]) -> Any:
        """Execute this webhook with an Instatus-shaped payload."""
        if not self._http:
            raise RuntimeError("Cannot execute webhook without HTTPClient")
        return await self._http.execute_instatus_webhook(self.id, self.token, payload)

    async def execute_slack(self, payload: dict[str, Any]) -> Any:
        """Execute this webhook with a Slack-shaped payload."""
        if not self._http:
            raise RuntimeError("Cannot execute webhook without HTTPClient")
        return await self._http.execute_slack_webhook(self.id, self.token, payload)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this webhook.

        Args:
            reason: Reason for deletion (shows in audit log)

        Raises:
            Forbidden: You don't have permission to delete this webhook
            NotFound: Webhook doesn't exist
            HTTPException: Deleting the webhook failed
        """
        if not self._http:
            raise RuntimeError("Cannot delete webhook without HTTPClient")

        await self._http.delete_webhook(self.id, reason=reason)
