from __future__ import annotations

import random


class ExponentialBackoff:
    def __init__(self, base: int = 1, *, integral: bool = False) -> None:
        self._base = base
        self._exp = 0
        self._max = 10
        self._integral = integral

    def delay(self) -> int | float:
        self._exp = min(self._exp + 1, self._max)
        upper = self._base * 2**self._exp
        if self._integral:
            return random.randrange(0, int(upper))
        return random.random() * upper

    def reset(self) -> None:
        self._exp = 0
