"""Asynchronous webhook handles and retained adapter compatibility names.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .._types import UNSET, UnsetType

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, unquote

from .user import User
from .message import Message, MessageReference, DeletedReferencedMessage
from .attachment import Attachment
from .reaction import Reaction
from ..sticker import Sticker

if TYPE_CHECKING:
    from ..file import File
    from ..http import HTTPClient


@dataclass(slots=True)
class WebhookMessage:
    """Message created by a Fluxer webhook.

    Attributes:
        id: The ID of the message.
        channel_id: The ID of the channel.
        content: The text of the message, empty when the message has only media.
        author: The user credited with the message.
        timestamp: Creation time derived from the message snowflake.
        edited_timestamp: Most recent edit time, or null when the message has never been edited.
        embeds: The previews resolved or supplied for the message.
        attachments: The files attached to the message.
        mentions: The users the message actively mentions.
        pinned: Whether the message is pinned.
        type: Message type.
        flags: Message flags.
        tts: Whether the message requested text-to-speech.
        mention_everyone: Whether the message mentions everyone.
        nonce: Caller-supplied message nonce, echoed to the sender as a string of 1 through 32 characters.
        call: Call state attached to a call message.
        mention_roles: The IDs of the roles the message actively mentions.
        mention_channels: The channels the message content links by ID.
        nsfw_emojis: IDs of the custom emojis in the message that are classified as explicit.
        users: Users referenced by non-notifying content, embed, and snapshot text.
        stickers: The stickers sent with the message.
        message_snapshots: The immutable copies captured for a forward.
        reactions: Reaction summaries.
        message_reference: Reply or forward reference.
        referenced_message: Resolved referenced message without a nested `referenced_message` field.
        webhook_id: Originating webhook ID, present only for a webhook-authored message.
        webhook_token: Webhook capability used for message edits and deletion; excluded from repr.
    """

    id: int
    channel_id: int
    content: str
    author: User
    timestamp: str
    edited_timestamp: str | None = None

    embeds: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    mentions: list[User] = field(default_factory=list)
    pinned: bool = False

    type: int = 0
    flags: int = 0
    tts: bool = False
    mention_everyone: bool = False
    nonce: str | None = None
    call: dict[str, Any] | None = None
    mention_roles: list[int] = field(default_factory=list)
    mention_channels: list[dict[str, Any]] = field(default_factory=list)
    nsfw_emojis: list[int] = field(default_factory=list)
    users: list[User] = field(default_factory=list)
    stickers: list[Sticker] = field(default_factory=list)
    message_snapshots: list[dict[str, Any]] = field(default_factory=list)
    reactions: list[Reaction] = field(default_factory=list)
    message_reference: MessageReference | None = None
    referenced_message: Message | DeletedReferencedMessage | None = None

    webhook_id: int | None = None
    webhook_token: str | None = field(default=None, repr=False)
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
        """Build a WebhookMessage from its decoded payload.

        Args:
            data: Decoded payload to parse; omitted fields retain the parser's documented defaults.
            http: Transport to bind for subsequent operations; None creates an unbound model.
            webhook_id: Identity of the webhook used by this operation.
            token: Caller-supplied credential or webhook capability; keep this value secret.

        Returns:
            A parsed WebhookMessage instance.
        """
        parsed = Message.from_data(data, http)
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
            webhook_id=int(webhook_id) if webhook_id is not None else parsed.webhook_id,
            webhook_token=token,
            type=parsed.type,
            flags=parsed.flags,
            tts=parsed.tts,
            mention_everyone=parsed.mention_everyone,
            nonce=parsed.nonce,
            call=parsed.call,
            mention_roles=parsed.mention_roles,
            mention_channels=parsed.mention_channels,
            nsfw_emojis=parsed.nsfw_emojis,
            users=parsed.users,
            stickers=parsed.stickers,
            message_snapshots=parsed.message_snapshots,
            reactions=parsed.reactions,
            message_reference=parsed.message_reference,
            referenced_message=parsed.referenced_message,
            _http=http,
        )

    async def edit(
        self, content: str | None | UnsetType = UNSET, **kwargs: Any
    ) -> WebhookMessage:
        """Edit.

        Args:
            content: Message text. On edits, omission preserves the text and None clears it.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        if self._http is None or self.webhook_id is None or self.webhook_token is None:
            raise RuntimeError("WebhookMessage is not bound to a webhook HTTP client")
        payload = {
            key: value
            for key, value in kwargs.items()
            if not isinstance(value, UnsetType)
        }
        if not isinstance(content, UnsetType):
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
        """Delete.

        Returns:
            None.
        """
        if self._http is None or self.webhook_id is None or self.webhook_token is None:
            raise RuntimeError("WebhookMessage is not bound to a webhook HTTP client")
        await self._http.delete_webhook_message(
            self.webhook_id,
            self.webhook_token,
            self.id,
        )


@dataclass(slots=True)
class Webhook:
    """Represents a Fluxer webhook.

    Attributes:
        id: Identity of the object used by this operation.
        guild_id: Guild identity retained from the payload or operation context.
        channel_id: Channel identity retained from the payload or operation context.
        user: User object or identity used by the operation.
        name: Name to assign or resolve in this operation.
        avatar: Replacement avatar; on an edit, omission preserves it and None clears it.
        token: Caller-supplied credential or webhook capability; keep this value secret.
    """

    id: int
    guild_id: int
    channel_id: int
    user: User | None
    name: str
    avatar: str | None
    token: str = field(repr=False)
    _token_only: bool = field(default=False, repr=False)
    _url_base: str | None = field(default=None, repr=False)

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_url(cls, url: str, *, http: HTTPClient | None = None) -> Webhook:
        """Create a webhook handle from a Fluxer webhook URL.

        Args:
            url: Absolute destination or resource URL.
            http: Transport to bind for subsequent operations; None creates an unbound model.

        Returns:
            A parsed Webhook instance.
        """
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Invalid Fluxer webhook URL")
        path = [part for part in parsed.path.split("/") if part]
        try:
            index = path.index("webhooks")
            webhook_id = int(path[index + 1])
            token = unquote(path[index + 2])
            if len(path) != index + 3:
                raise ValueError("Unexpected webhook URL suffix")
        except (ValueError, IndexError) as exc:
            raise ValueError("Invalid Fluxer webhook URL") from exc

        return cls(
            id=webhook_id,
            guild_id=0,
            channel_id=0,
            user=None,
            name="Webhook",
            avatar=None,
            token=token,
            _token_only=True,
            _url_base=f"{parsed.scheme}://{parsed.netloc}/" + "/".join(path[:index]),
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
            guild_id=guild_id
            if guild_id is not None
            else int(data.get("guild_id") or 0),
            channel_id=int(data["channel_id"]),
            user=User.from_data(data["user"], http)
            if data.get("user") is not None
            else None,
            name=data["name"],
            avatar=data.get("avatar", None),
            token=data.get("token", ""),
            _token_only="user" not in data,
            _http=http,
        )

    async def edit(
        self,
        *,
        name: str | None = None,
        avatar: str | None | UnsetType = UNSET,
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

        await self._validate_authority()
        if self._token_only:
            data = await self._http.modify_webhook_with_token(
                self.id,
                self.token,
                name=name,
                avatar=avatar,
                channel_id=channel_id,
            )
        else:
            data = await self._http.modify_webhook(
                self.id,
                name=name,
                avatar=avatar,
                channel_id=channel_id,
            )
        updated = Webhook.from_data(data, self._http)
        updated.token = updated.token or self.token
        updated._token_only = self._token_only
        updated._url_base = self._url_base
        return updated

    async def _validate_authority(self) -> None:
        if self._url_base is None or self._http is None:
            return
        from ..http import HTTPClient

        if isinstance(self._http, HTTPClient):
            await self._http._ensure_session()
            if self._http.api_url != self._url_base.rstrip("/"):
                raise ValueError(
                    "Webhook URL belongs to another API; bind a client with that api_url"
                )

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
            allowed_mentions: Mention policy, including explicit empty selections and false flags.
            message_reference: Reply or forward reference and any explicit attachment/embed selections.
            flags: Bit mask governing the object's documented flags.
            nonce: Caller-selected correlation value echoed by the operation when supported.
            favorite_meme_id: Identity of the favorite meme used by this operation.
            sticker_ids: IDs of the sticker resources selected by this operation.
            tts: Whether the message requests text-to-speech playback.

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

        await self._validate_authority()
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
        content: str | None | UnsetType = UNSET,
        embeds: list[dict[str, Any]] | None = None,
        allowed_mentions: Any | None | UnsetType = UNSET,
        flags: int | None = None,
    ) -> WebhookMessage:
        """Edit a message previously created by this webhook.

        Args:
            message_id: Identity of the message used by this operation.
            content: Message text. On edits, omission preserves the text and None clears it.
            embeds: Rich embeds in display order; an empty list removes them on an edit.
            allowed_mentions: Mention policy, including explicit empty selections and false flags.
            flags: Bit mask governing the object's documented flags.

        Returns:
            The result of this operation.
        """
        if not self._http:
            raise RuntimeError("Cannot edit webhook message without HTTPClient")
        payload: dict[str, Any] = {}
        if not isinstance(content, UnsetType):
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds
        if not isinstance(allowed_mentions, UnsetType):
            payload["allowed_mentions"] = allowed_mentions
        if flags is not None:
            payload["flags"] = flags

        await self._validate_authority()
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
        """Delete a message previously created by this webhook.

        Args:
            message_id: Identity of the message used by this operation.

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot delete webhook message without HTTPClient")
        await self._validate_authority()
        await self._http.delete_webhook_message(self.id, self.token, message_id)

    async def execute_github(
        self,
        payload: dict[str, Any],
        *,
        event: str | None = None,
        delivery: str | None = None,
    ) -> None:
        """Execute this webhook with a GitHub-shaped payload.

        Args:
            payload: Operation-specific fields in the documented request shape.
            event: Event name used for registration or webhook callback headers.
            delivery: GitHub delivery identifier used for callback deduplication.

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot execute webhook without HTTPClient")
        await self._validate_authority()
        return await self._http.execute_github_webhook(
            self.id, self.token, payload, event=event, delivery=delivery
        )

    async def execute_instatus(self, payload: dict[str, Any]) -> None:
        """Execute this webhook with an Instatus-shaped payload.

        Args:
            payload: Operation-specific fields in the documented request shape.

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot execute webhook without HTTPClient")
        await self._validate_authority()
        return await self._http.execute_instatus_webhook(self.id, self.token, payload)

    async def execute_slack(self, payload: dict[str, Any]) -> str:
        """Execute this webhook with a Slack-shaped payload.

        Args:
            payload: Operation-specific fields in the documented request shape.

        Returns:
            The result of this operation.
        """
        if not self._http:
            raise RuntimeError("Cannot execute webhook without HTTPClient")
        await self._validate_authority()
        return await self._http.execute_slack_webhook(self.id, self.token, payload)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this webhook.

        Args:
            reason: Reason for deletion (shows in audit log)

        Raises:
            Forbidden: You don't have permission to delete this webhook
            NotFound: Webhook doesn't exist
            HTTPException: Deleting the webhook failed

        Returns:
            None.
        """
        if not self._http:
            raise RuntimeError("Cannot delete webhook without HTTPClient")

        await self._validate_authority()
        if self._token_only:
            await self._http.delete_webhook_with_token(self.id, self.token)
        else:
            await self._http.delete_webhook(self.id, reason=reason)


__all__ = ("WebhookMessage", "Webhook")
