"""Context helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .view import StringView
    from .bot import Bot
    from .core import Command
    from ...models import Channel, Guild, Message, User


class Context:
    """Parsed command invocation context.

    The message supplies identity and channel/guild context; callback arguments are
    populated during command preparation.

    Attributes:
        bot: Bot client or bot-user metadata associated with this object.
        message: Message.
        prefix: Resolved command prefix, or None when the message matched no prefix.
        command: Resolved command, or None when lookup did not find a command.
        invoked_with: Command name entered by the caller, before alias resolution.
        view: View used by this operation.
        args: Positional arguments retained by this object.
        kwargs: Keyword arguments retained by this object.
        valid: Return whether a command was resolved for this context.
        guild: Return the guild cached for this invocation.
        channel: Return the channel cached for this invocation.
        author: Return the user who authored the command message.
    """

    bot: Bot
    message: Message
    prefix: str | None
    command: Command | None
    invoked_with: str | None

    def __init__(self, **attrs: Any) -> None:
        """Initialize the context with the supplied configuration.

        Args:
            **attrs: Attrs used by this operation.
        """
        self.bot = attrs["bot"]
        self.message = attrs["message"]
        self.prefix = attrs.get("prefix")
        self.command = attrs.get("command")
        self.invoked_with = attrs.get("invoked_with")
        self.view: StringView | None = attrs.get("view")
        self.args: list[Any] = []
        self.kwargs: dict[str, Any] = {}

    @property
    def valid(self) -> bool:
        """Return whether a command was resolved for this context.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.command is not None

    @property
    def guild(self) -> Guild | None:
        """Return the guild cached for this invocation.

        Returns:
            The result of this operation.
        """
        return self.message.guild

    @property
    def channel(self) -> Channel | None:
        """Return the channel cached for this invocation.

        Returns:
            The result of this operation.
        """
        return self.message.channel

    @property
    def author(self) -> User:
        """Return the user who authored the command message.

        Returns:
            The result of this operation.
        """
        return self.message.author

    async def send(self, content: str | None = None, **kwargs: Any) -> Message:
        """Send a message to the invocation channel.

        Args:
            content: Text content sent in the message.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        return await self.message.send(content, **kwargs)

    async def reply(self, content: str | None = None, **kwargs: Any) -> Message:
        """Reply to the invocation message.

        Args:
            content: Text content sent in the message.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        return await self.message.reply(content, **kwargs)

    async def invoke(self, command: Command, /, *args: Any, **kwargs: Any) -> Any:
        """Invoke the selected command with its parsed context.

        Args:
            command: Command to resolve, invoke, or display.
            *args: Positional arguments forwarded to the wrapped callback.
            **kwargs: Additional options forwarded to the underlying operation.

        Returns:
            The result of this operation.
        """
        self.command = command
        self.args = [self, *args]
        self.kwargs = kwargs
        return await command.callback(*self.args, **self.kwargs)

    async def reinvoke(self, *, call_hooks: bool = False, restart: bool = True) -> Any:
        """Invoke the context's command again with the selected hook behaviour.

        Args:
            call_hooks: Call hooks used by this operation.
            restart: Restart used by this operation.

        Returns:
            The result of this operation.
        """
        if self.command is None:
            return None
        return await self.command.invoke(self)

    async def send_help(self, *args: Any) -> Any:
        """Send help.

        Args:
            *args: Positional arguments forwarded to the wrapped callback.

        Returns:
            The result of this operation.
        """
        if self.bot.help_command is None:
            return None
        return await self.bot.help_command.command_callback(
            self, command=" ".join(map(str, args)) or None
        )


__all__ = ("Context",)
