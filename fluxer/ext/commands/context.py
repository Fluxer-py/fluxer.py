from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .view import StringView


class Context:
    def __init__(self, **attrs: Any) -> None:
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
        return self.command is not None

    @property
    def guild(self) -> Any:
        return self.message.guild

    @property
    def channel(self) -> Any:
        return self.message.channel

    @property
    def author(self) -> Any:
        return self.message.author

    async def send(self, content: str | None = None, **kwargs: Any) -> Any:
        return await self.message.send(content, **kwargs)

    async def reply(self, content: str | None = None, **kwargs: Any) -> Any:
        return await self.message.reply(content, **kwargs)

    async def invoke(self, command: Any, /, *args: Any, **kwargs: Any) -> Any:
        self.command = command
        self.args = [self, *args]
        self.kwargs = kwargs
        return await command.callback(*self.args, **self.kwargs)

    async def reinvoke(self, *, call_hooks: bool = False, restart: bool = True) -> Any:
        if self.command is None:
            return None
        return await self.command.invoke(self)

    async def send_help(self, *args: Any) -> Any:
        if self.bot.help_command is None:
            return None
        return await self.bot.help_command.command_callback(
            self, command=" ".join(map(str, args)) or None
        )
