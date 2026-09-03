from __future__ import annotations

from ...errors import FluxerException


class CommandError(FluxerException):
    pass


class ConversionError(CommandError):
    def __init__(self, converter: object, original: Exception) -> None:
        self.converter = converter
        self.original = original
        super().__init__(f"{converter!r} failed to convert: {original}")


class UserInputError(CommandError):
    pass


class CommandNotFound(CommandError):
    pass


class MissingRequiredArgument(UserInputError):
    def __init__(self, param: object) -> None:
        self.param = param
        super().__init__(f"Missing required argument: {getattr(param, 'name', param)}")


class TooManyArguments(UserInputError):
    pass


class BadArgument(UserInputError):
    pass


class BadBoolArgument(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"{argument!r} is not a recognised boolean option")


class MemberNotFound(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"Member {argument!r} was not found")


class GuildNotFound(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"Guild {argument!r} was not found")


class UserNotFound(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"User {argument!r} was not found")


class MessageNotFound(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"Message {argument!r} was not found")


class ChannelNotFound(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"Channel {argument!r} was not found")


class RoleNotFound(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"Role {argument!r} was not found")


class EmojiNotFound(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"Emoji {argument!r} was not found")


class BadColourArgument(BadArgument):
    def __init__(self, argument: str) -> None:
        super().__init__(f"Colour {argument!r} is invalid")


class BadUnionArgument(UserInputError):
    def __init__(
        self, param: object, converters: tuple[object, ...], errors: list[Exception]
    ) -> None:
        self.param = param
        self.converters = converters
        self.errors = errors
        names = ", ".join(
            getattr(converter, "__name__", repr(converter)) for converter in converters
        )
        super().__init__(
            f"Could not convert {getattr(param, 'name', param)} into any of: {names}"
        )


class ArgumentParsingError(UserInputError):
    pass


class UnexpectedQuoteError(ArgumentParsingError):
    def __init__(self, quote: str) -> None:
        self.quote = quote
        super().__init__(f"Unexpected quote mark {quote!r} in argument")


class InvalidEndOfQuotedStringError(ArgumentParsingError):
    def __init__(self, char: str) -> None:
        self.char = char
        super().__init__(f"Expected space after closing quote but received {char!r}")


class ExpectedClosingQuoteError(ArgumentParsingError):
    def __init__(self, close_quote: str) -> None:
        self.close_quote = close_quote
        super().__init__(f"Expected closing quote {close_quote!r}")


class CheckFailure(CommandError):
    pass


class CheckAnyFailure(CheckFailure):
    def __init__(self, checks: list[object], errors: list[Exception]) -> None:
        self.checks = checks
        self.errors = errors
        super().__init__("All checks failed")


class DisabledCommand(CommandError):
    pass


class CommandInvokeError(CommandError):
    def __init__(self, original: Exception) -> None:
        self.original = original
        super().__init__(f"Command raised an exception: {original!r}")


class CommandOnCooldown(CommandError):
    def __init__(self, cooldown: object, retry_after: float) -> None:
        self.cooldown = cooldown
        self.retry_after = retry_after
        super().__init__(f"You are on cooldown. Try again in {retry_after:.2f}s")


class MaxConcurrencyReached(CommandError):
    pass


class NotOwner(CheckFailure):
    pass


class MissingRole(CheckFailure):
    pass


class MissingAnyRole(CheckFailure):
    pass


class MissingPermissions(CheckFailure):
    def __init__(self, missing_permissions: list[str]) -> None:
        self.missing_permissions = missing_permissions
        super().__init__("Missing permissions: " + ", ".join(missing_permissions))


class BotMissingPermissions(MissingPermissions):
    pass


class BotMissingRole(MissingRole):
    pass


class BotMissingAnyRole(MissingAnyRole):
    pass


class NSFWChannelRequired(CheckFailure):
    pass


class NoPrivateMessage(CheckFailure):
    pass


class PrivateMessageOnly(CheckFailure):
    pass


class ExtensionError(FluxerException):
    def __init__(self, message: str | None = None, *, name: str) -> None:
        self.name = name
        super().__init__(message or f"Extension {name!r} had an error")


class ExtensionAlreadyLoaded(ExtensionError):
    pass


class ExtensionNotLoaded(ExtensionError):
    pass


class NoEntryPointError(ExtensionError):
    pass


class ExtensionFailed(ExtensionError):
    def __init__(self, name: str, original: Exception) -> None:
        self.original = original
        super().__init__(f"Extension {name!r} raised an error: {original!r}", name=name)


class ExtensionNotFound(ExtensionError):
    pass


class CommandRegistrationError(FluxerException):
    pass
