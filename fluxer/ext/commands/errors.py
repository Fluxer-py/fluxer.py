"""Errors helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from ...errors import FluxerException


class CommandError(FluxerException):
    """Exception indicating command error.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class ConversionError(CommandError):
    """Exception indicating conversion error.

    Attributes:
        args: Exception arguments retained by Python.
        converter: Converter applied to the command argument.
        original: Original exception retained for diagnostics.
    """

    def __init__(self, converter: object, original: Exception) -> None:
        """Initialize the conversion error with the supplied configuration.

        Args:
            converter: Converter applied to the command argument.
            original: Original exception retained for diagnostics.
        """
        self.converter: object = converter
        self.original: Exception = original
        super().__init__(f"{converter!r} failed to convert: {original}")


class UserInputError(CommandError):
    """Exception indicating user input error.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class CommandNotFound(CommandError):
    """Exception indicating command not found.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class MissingRequiredArgument(UserInputError):
    """Exception indicating missing required argument.

    Attributes:
        args: Exception arguments retained by Python.
        param: Parameter metadata identifying the argument being processed.
    """

    def __init__(self, param: object) -> None:
        """Initialize the missing required argument with the supplied configuration.

        Args:
            param: Parameter metadata identifying the argument being processed.
        """
        self.param: object = param
        super().__init__(f"Missing required argument: {getattr(param, 'name', param)}")


class TooManyArguments(UserInputError):
    """Exception indicating too many arguments.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class BadArgument(UserInputError):
    """Exception indicating bad argument.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class BadBoolArgument(BadArgument):
    """Bad Bool Argument data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the bad bool argument with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"{argument!r} is not a recognised boolean option")


class MemberNotFound(BadArgument):
    """Member Not Found data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the member not found with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"Member {argument!r} was not found")


class GuildNotFound(BadArgument):
    """Guild Not Found data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the guild not found with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"Guild {argument!r} was not found")


class UserNotFound(BadArgument):
    """User Not Found data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the user not found with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"User {argument!r} was not found")


class MessageNotFound(BadArgument):
    """Message Not Found data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the message not found with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"Message {argument!r} was not found")


class ChannelNotFound(BadArgument):
    """Channel Not Found data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the channel not found with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"Channel {argument!r} was not found")


class RoleNotFound(BadArgument):
    """Role Not Found data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the role not found with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"Role {argument!r} was not found")


class EmojiNotFound(BadArgument):
    """Emoji Not Found data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the emoji not found with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"Emoji {argument!r} was not found")


class BadColourArgument(BadArgument):
    """Bad Colour Argument data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    def __init__(self, argument: str) -> None:
        """Initialize the bad colour argument with the supplied configuration.

        Args:
            argument: Unconverted command argument text.
        """
        super().__init__(f"Colour {argument!r} is invalid")


class BadUnionArgument(UserInputError):
    """Exception indicating bad union argument.

    Attributes:
        args: Exception arguments retained by Python.
        param: Parameter metadata identifying the argument being processed.
        converters: Alternative converters tried for this argument.
        errors: Validation or conversion failures retained for caller inspection.
    """

    def __init__(
        self, param: object, converters: tuple[object, ...], errors: list[Exception]
    ) -> None:
        """Initialize the bad union argument with the supplied configuration.

        Args:
            param: Parameter metadata identifying the argument being processed.
            converters: Alternative converters tried for this argument.
            errors: Validation or conversion failures retained for caller inspection.
        """
        self.param: object = param
        self.converters: tuple[object, ...] = converters
        self.errors: list[Exception] = errors
        names = ", ".join(
            getattr(converter, "__name__", repr(converter)) for converter in converters
        )
        super().__init__(
            f"Could not convert {getattr(param, 'name', param)} into any of: {names}"
        )


class ArgumentParsingError(UserInputError):
    """Exception indicating argument parsing error.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class UnexpectedQuoteError(ArgumentParsingError):
    """Exception indicating unexpected quote error.

    Attributes:
        args: Exception arguments retained by Python.
        quote: Quote used by this operation.
    """

    def __init__(self, quote: str) -> None:
        """Initialize the unexpected quote error with the supplied configuration.

        Args:
            quote: Quote used by this operation.
        """
        self.quote: str = quote
        super().__init__(f"Unexpected quote mark {quote!r} in argument")


class InvalidEndOfQuotedStringError(ArgumentParsingError):
    """Exception indicating invalid end of quoted string error.

    Attributes:
        args: Exception arguments retained by Python.
        char: Char used by this operation.
    """

    def __init__(self, char: str) -> None:
        """Initialize the invalid end of quoted string error with the supplied configuration.

        Args:
            char: Char used by this operation.
        """
        self.char: str = char
        super().__init__(f"Expected space after closing quote but received {char!r}")


class ExpectedClosingQuoteError(ArgumentParsingError):
    """Exception indicating expected closing quote error.

    Attributes:
        args: Exception arguments retained by Python.
        close_quote: Close quote used by this operation.
    """

    def __init__(self, close_quote: str) -> None:
        """Initialize the expected closing quote error with the supplied configuration.

        Args:
            close_quote: Close quote used by this operation.
        """
        self.close_quote: str = close_quote
        super().__init__(f"Expected closing quote {close_quote!r}")


class CheckFailure(CommandError):
    """Exception indicating check failure.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class CheckAnyFailure(CheckFailure):
    """Check Any Failure data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
        checks: Alternative conditions evaluated by the check decorator.
        errors: Validation or conversion failures retained for caller inspection.
    """

    def __init__(self, checks: list[object], errors: list[Exception]) -> None:
        """Initialize the check any failure with the supplied configuration.

        Args:
            checks: Alternative conditions evaluated by the check decorator.
            errors: Validation or conversion failures retained for caller inspection.
        """
        self.checks: list[object] = checks
        self.errors: list[Exception] = errors
        super().__init__("All checks failed")


class DisabledCommand(CommandError):
    """Exception indicating disabled command.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class CommandInvokeError(CommandError):
    """Exception indicating command invoke error.

    Attributes:
        args: Exception arguments retained by Python.
        original: Original exception retained for diagnostics.
    """

    def __init__(self, original: Exception) -> None:
        """Initialize the command invoke error with the supplied configuration.

        Args:
            original: Original exception retained for diagnostics.
        """
        self.original: Exception = original
        super().__init__(f"Command raised an exception: {original!r}")


class CommandOnCooldown(CommandError):
    """Exception indicating command on cooldown.

    Attributes:
        args: Exception arguments retained by Python.
        cooldown: Cooldown used by this operation.
        retry_after: Fractional seconds until the next request may be admitted.
    """

    def __init__(self, cooldown: object, retry_after: float) -> None:
        """Initialize the command on cooldown with the supplied configuration.

        Args:
            cooldown: Cooldown used by this operation.
            retry_after: Fractional seconds until the next request may be admitted.
        """
        self.cooldown: object = cooldown
        self.retry_after: float = retry_after
        super().__init__(f"You are on cooldown. Try again in {retry_after:.2f}s")


class MaxConcurrencyReached(CommandError):
    """Exception indicating max concurrency reached.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class NotOwner(CheckFailure):
    """Not Owner data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class MissingRole(CheckFailure):
    """Missing Role data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class MissingAnyRole(CheckFailure):
    """Missing Any Role data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class MissingPermissions(CheckFailure):
    """Missing Permissions data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
        missing_permissions: Missing permissions used by this operation.
    """

    def __init__(self, missing_permissions: list[str]) -> None:
        """Initialize the missing permissions with the supplied configuration.

        Args:
            missing_permissions: Missing permissions used by this operation.
        """
        self.missing_permissions: list[str] = missing_permissions
        super().__init__("Missing permissions: " + ", ".join(missing_permissions))


class BotMissingPermissions(MissingPermissions):
    """Bot Missing Permissions data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
        missing_permissions: Missing permissions used by this operation.
    """

    pass


class BotMissingRole(MissingRole):
    """Bot Missing Role data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class BotMissingAnyRole(MissingAnyRole):
    """Bot Missing Any Role data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class NSFWChannelRequired(CheckFailure):
    """NSFWChannel Required data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class NoPrivateMessage(CheckFailure):
    """No Private Message data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class PrivateMessageOnly(CheckFailure):
    """Private Message Only data and behaviour.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


class ExtensionError(FluxerException):
    """Exception indicating extension error.

    Attributes:
        name: Name to assign or resolve in this operation.
    """

    def __init__(self, message: str | None = None, *, name: str) -> None:
        """Initialize the extension error with the supplied configuration.

        Args:
            message: Server-provided failure description.
            name: Name to assign or resolve in this operation.
        """
        self.name: str = name
        super().__init__(message or f"Extension {name!r} had an error")


class ExtensionAlreadyLoaded(ExtensionError):
    """Exception indicating extension already loaded.

    Attributes:
        name: Name to assign or resolve in this operation.
    """

    pass


class ExtensionNotLoaded(ExtensionError):
    """Exception indicating extension not loaded.

    Attributes:
        name: Name to assign or resolve in this operation.
    """

    pass


class NoEntryPointError(ExtensionError):
    """Exception indicating no entry point error.

    Attributes:
        name: Name to assign or resolve in this operation.
    """

    pass


class ExtensionFailed(ExtensionError):
    """Exception indicating extension failed.

    Attributes:
        name: Name to assign or resolve in this operation.
        original: Original exception retained for diagnostics.
    """

    def __init__(self, name: str, original: Exception) -> None:
        """Initialize the extension failed with the supplied configuration.

        Args:
            name: Name to assign or resolve in this operation.
            original: Original exception retained for diagnostics.
        """
        self.original: Exception = original
        super().__init__(f"Extension {name!r} raised an error: {original!r}", name=name)


class ExtensionNotFound(ExtensionError):
    """Exception indicating extension not found.

    Attributes:
        name: Name to assign or resolve in this operation.
    """

    pass


class CommandRegistrationError(FluxerException):
    """Exception indicating command registration error.

    Attributes:
        args: Exception arguments retained by Python.
    """

    pass


__all__ = (
    "CommandError",
    "ConversionError",
    "UserInputError",
    "CommandNotFound",
    "MissingRequiredArgument",
    "TooManyArguments",
    "BadArgument",
    "BadBoolArgument",
    "MemberNotFound",
    "GuildNotFound",
    "UserNotFound",
    "MessageNotFound",
    "ChannelNotFound",
    "RoleNotFound",
    "EmojiNotFound",
    "BadColourArgument",
    "BadUnionArgument",
    "ArgumentParsingError",
    "UnexpectedQuoteError",
    "InvalidEndOfQuotedStringError",
    "ExpectedClosingQuoteError",
    "CheckFailure",
    "CheckAnyFailure",
    "DisabledCommand",
    "CommandInvokeError",
    "CommandOnCooldown",
    "MaxConcurrencyReached",
    "NotOwner",
    "MissingRole",
    "MissingAnyRole",
    "MissingPermissions",
    "BotMissingPermissions",
    "BotMissingRole",
    "BotMissingAnyRole",
    "NSFWChannelRequired",
    "NoPrivateMessage",
    "PrivateMessageOnly",
    "ExtensionError",
    "ExtensionAlreadyLoaded",
    "ExtensionNotLoaded",
    "NoEntryPointError",
    "ExtensionFailed",
    "ExtensionNotFound",
    "CommandRegistrationError",
)
