"""Backoff helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import random


class ExponentialBackoff:
    """Capped exponential backoff with uniformly sampled jitter.

    Attributes:
        _base: Base delay scale in seconds.
        _exp: Current bounded exponent, reset by reset().
    """

    def __init__(self, base: int = 1, *, integral: bool = False) -> None:
        """Initialize the exponential backoff with the supplied configuration.

        Args:
            base: Base delay used by the exponential backoff calculation.
            integral: Whether delay values are sampled as whole seconds.
        """
        self._base = base
        self._exp = 0
        self._max = 10
        self._integral = integral

    def delay(self) -> int | float:
        """Sample the next delay from the capped exponential backoff window.

        Returns:
            The result of this operation.
        """
        self._exp = min(self._exp + 1, self._max)
        upper = self._base * 2**self._exp
        if self._integral:
            return random.randrange(0, int(upper))
        return random.random() * upper

    def reset(self) -> None:
        """Reset.

        Returns:
            None.
        """
        self._exp = 0


__all__ = ("ExponentialBackoff",)
