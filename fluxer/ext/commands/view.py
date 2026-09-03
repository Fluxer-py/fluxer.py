from __future__ import annotations

import re


class StringView:
    def __init__(self, buffer: str) -> None:
        self.buffer = buffer
        self.index = 0
        self.previous = 0

    @property
    def current(self) -> str | None:
        return None if self.eof else self.buffer[self.index]

    @property
    def eof(self) -> bool:
        return self.index >= len(self.buffer)

    def undo(self) -> None:
        self.index = self.previous

    def skip_ws(self) -> bool:
        pos = self.index
        while not self.eof and self.buffer[self.index].isspace():
            self.index += 1
        return self.index > pos

    def skip_string(self, string: str) -> bool:
        if self.buffer.startswith(string, self.index):
            self.previous = self.index
            self.index += len(string)
            return True
        return False

    def read_rest(self) -> str:
        result = self.buffer[self.index :]
        self.previous = self.index
        self.index = len(self.buffer)
        return result

    def get_word(self) -> str:
        self.skip_ws()
        self.previous = self.index
        while not self.eof and not self.buffer[self.index].isspace():
            self.index += 1
        return self.buffer[self.previous : self.index]

    def get_quoted_word(self) -> str:
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
        if isinstance(prefixes, str):
            prefixes = (prefixes,)
        for prefix in sorted(prefixes, key=len, reverse=True):
            if self.buffer.startswith(prefix):
                return prefix
        return None


MENTION_RE = re.compile(r"^<@!?(\d+)>\s*")
