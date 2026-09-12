"""View helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import re


class StringView:
    """Cursor over command argument text with whitespace and quoted-word parsing.

    Attributes:
        buffer: Original command argument text.
        index: Zero-based position in the current sequence.
        previous: Position saved before the previous read, used by undo().
        current: Return the character at the current parser position, when available.
        eof: Return whether the parser has reached the end of its input.
    """

    def __init__(self, buffer: str) -> None:
        """Initialize the string view with the supplied configuration.

        Args:
            buffer: Original command argument text.
        """
        self.buffer: str = buffer
        self.index: int = 0
        self.previous: int = 0

    @property
    def current(self) -> str | None:
        """Return the character at the current parser position, when available.

        Returns:
            The result of this operation.
        """
        return None if self.eof else self.buffer[self.index]

    @property
    def eof(self) -> bool:
        """Return whether the parser has reached the end of its input.

        Returns:
            Whether the documented condition holds for the current state.
        """
        return self.index >= len(self.buffer)

    def undo(self) -> None:
        """Restore the parser position saved before the last read.

        Returns:
            None.
        """
        self.index = self.previous

    def skip_ws(self) -> bool:
        """Advance past whitespace and report whether the position changed.

        Returns:
            Whether the documented condition holds for the current state.
        """
        pos = self.index
        while not self.eof and self.buffer[self.index].isspace():
            self.index += 1
        return self.index > pos

    def skip_string(self, string: str) -> bool:
        """Consume a matching literal at the current parser position.

        Args:
            string: Text being parsed or matched.

        Returns:
            Whether the documented condition holds for the current state.
        """
        if self.buffer.startswith(string, self.index):
            self.previous = self.index
            self.index += len(string)
            return True
        return False

    def read_rest(self) -> str:
        """Consume and return the unparsed remainder of the argument text.

        Returns:
            The result of this operation.
        """
        result = self.buffer[self.index :]
        self.previous = self.index
        self.index = len(self.buffer)
        return result

    def get_word(self) -> str:
        """Consume the next whitespace-delimited argument.

        Returns:
            The requested word.
        """
        self.skip_ws()
        self.previous = self.index
        while not self.eof and not self.buffer[self.index].isspace():
            self.index += 1
        return self.buffer[self.previous : self.index]

    def get_quoted_word(self) -> str:
        """Consume the next argument, interpreting the supported quotation syntax.

        Returns:
            The requested quoted word.
        """
        from .errors import ExpectedClosingQuoteError, InvalidEndOfQuotedStringError

        self.skip_ws()
        if self.eof:
            return ""
        quote = self.buffer[self.index]
        if quote not in {'"', "'"}:
            return self.get_word()
        self.previous = self.index
        self.index += 1
        escaped = False
        out: list[str] = []
        closed = False
        while not self.eof:
            ch = self.buffer[self.index]
            self.index += 1
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                closed = True
                break
            else:
                out.append(ch)
        if not closed:
            raise ExpectedClosingQuoteError(quote)
        if not self.eof and not self.buffer[self.index].isspace():
            raise InvalidEndOfQuotedStringError(self.buffer[self.index])
        return "".join(out)

    def find_prefix(self, prefixes: str | list[str] | tuple[str, ...]) -> str | None:
        """Find a matching command prefix in the parser's input.

        Args:
            prefixes: Prefixes used by this operation.

        Returns:
            The result of this operation.
        """
        if isinstance(prefixes, str):
            prefixes = (prefixes,)
        for prefix in sorted(prefixes, key=len, reverse=True):
            if self.buffer.startswith(prefix):
                return prefix
        return None


MENTION_RE = re.compile(r"^<@!?(\d+)>\s*")


__all__ = ("StringView",)
