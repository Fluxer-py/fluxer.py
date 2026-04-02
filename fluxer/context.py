from typing import TYPE_CHECKING, Any

from fluxer.file import File
from fluxer.models.message import Message

if TYPE_CHECKING:
    from fluxer.client import Bot


class Context:
    r"""Represents the context in which a command is being invoked under.

    This is not usually created manually, instead it is created by the bot when a command is being invoked. It contains information about the command being invoked.
    """

    def __init__(self, **attrs):
        self.message: Message = attrs.pop("message", None)
        self.bot: Bot = attrs.pop("bot", None)
        self.args = attrs.pop("args", [])
        self.kwargs = attrs.pop("kwargs", {})
        self.prefix: str = attrs.pop("prefix")

    @property
    def valid(self):
        """Checks if the invocation context is valid to be invoked with."""
        return self.prefix is not None

    @property
    def guild(self):
        return self.message.guild

    @property
    def channel(self):
        return self.message.channel

    @property
    def author(self):
        return self.message.author

    @property
    def me(self):
        return self.bot.user

    async def send(
        self,
        content: str | None = None,
        *,
        embed: Any | None = None,
        embeds: list[Any] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        **kwargs: Any,
    ) -> Message:
        return await self.message.send(
            content, embed=embed, embeds=embeds, file=file, files=files, **kwargs
        )

    async def reply(
        self,
        content: str | None = None,
        *,
        embed: Any | None = None,
        embeds: list[Any] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        **kwargs: Any,
    ) -> Message:
        return await self.message.reply(
            content, embed=embed, embeds=embeds, file=file, files=files, **kwargs
        )
