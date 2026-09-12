"""Cooldowns helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any


class BucketType(Enum):
    """Bucket Type data and behaviour.

    Attributes:
        name: Symbolic name of this enumeration member.
        value: Numeric wire or compatibility value of this member.
    """

    default = 0
    user = 1
    guild = 2
    channel = 3
    member = 4

    def get_key(self, message: Any) -> Any:
        """Derive the command bucket key from its invocation context.

        Args:
            message: Message supplying content and channel/guild context.

        Returns:
            The requested key.
        """
        if self is BucketType.user:
            return getattr(getattr(message, "author", None), "id", None)
        if self is BucketType.guild:
            return getattr(message, "guild_id", None)
        if self is BucketType.channel:
            return getattr(message, "channel_id", None)
        if self is BucketType.member:
            return (
                getattr(message, "guild_id", None),
                getattr(getattr(message, "author", None), "id", None),
            )
        return None


class Cooldown:
    """Cooldown data and behaviour.

    Attributes:
        rate: Rate.
        per: Per.
        type: Type used by this operation.
    """

    rate: int
    per: float

    def __init__(
        self, rate: int, per: float, type: BucketType = BucketType.default
    ) -> None:
        """Initialize the cooldown with the supplied configuration.

        Args:
            rate: Number of uses permitted during the local cooldown interval.
            per: Length of the local cooldown interval in seconds.
            type: Type used by this operation.
        """
        self.rate = int(rate)
        self.per = float(per)
        self.type: BucketType = type
        self._tokens = self.rate
        self._window = 0.0
        self._last = 0.0

    def copy(self) -> "Cooldown":
        """Copy.

        Returns:
            The result of this operation.
        """
        return Cooldown(self.rate, self.per, self.type)

    def get_tokens(self, current: float | None = None) -> int:
        """Return the local cooldown tokens available at the supplied time.

        Args:
            current: Clock value used when calculating cooldown state.

        Returns:
            The requested tokens.
        """
        current = current or time.time()
        if current > self._window + self.per:
            return self.rate
        return self._tokens

    def get_retry_after(self, current: float | None = None) -> float:
        """Return the delay before the local cooldown admits another invocation.

        Args:
            current: Clock value used when calculating cooldown state.

        Returns:
            The requested retry after.
        """
        current = current or time.time()
        tokens = self.get_tokens(current)
        if tokens == 0:
            return max(self.per - (current - self._window), 0.0)
        return 0.0

    def update_rate_limit(self, current: float | None = None) -> float | None:
        """Consume local cooldown tokens and return any required retry delay.

        Args:
            current: Clock value used when calculating cooldown state.

        Returns:
            The result of this operation.
        """
        current = current or time.time()
        self._last = current
        self._tokens = self.get_tokens(current)
        if self._tokens == self.rate:
            self._window = current
        if self._tokens == 0:
            return self.get_retry_after(current)
        self._tokens -= 1
        return None

    def reset(self) -> None:
        """Reset.

        Returns:
            None.
        """
        self._tokens = self.rate
        self._last = 0.0


class CooldownMapping:
    """Cooldown Mapping data and behaviour.

    Attributes:
        get_bucket: Resolve the independently tracked cooldown for an invocation.
    """

    def __init__(self, original: Cooldown | None) -> None:
        """Initialize the cooldown mapping with the supplied configuration.

        Args:
            original: Original exception retained for diagnostics.
        """
        self._cooldown = original
        self._cache: dict[Any, Cooldown] = {}

    @classmethod
    def from_cooldown(
        cls, rate: int, per: float, type: BucketType
    ) -> "CooldownMapping":
        """Build independent cooldown buckets from one rate configuration.

        Args:
            rate: Number of uses permitted during the local cooldown interval.
            per: Length of the local cooldown interval in seconds.
            type: Type used by this operation.

        Returns:
            A parsed CooldownMapping instance.
        """
        return cls(Cooldown(rate, per, type))

    def copy(self) -> "CooldownMapping":
        """Copy.

        Returns:
            The result of this operation.
        """
        return CooldownMapping(self._cooldown.copy() if self._cooldown else None)

    def get_bucket(self, message: Any, current: float | None = None) -> Cooldown | None:
        """Resolve the local cooldown bucket for a message.

        Args:
            message: Message supplying content and channel/guild context.
            current: Clock value used when calculating cooldown state.

        Returns:
            The requested bucket, or None when no matching value is available.
        """
        if self._cooldown is None:
            return None
        key = self._cooldown.type.get_key(message)
        if key not in self._cache:
            self._cache[key] = self._cooldown.copy()
        return self._cache[key]

    def update_rate_limit(
        self, message: Any, current: float | None = None
    ) -> float | None:
        """Consume local cooldown tokens and return any required retry delay.

        Args:
            message: Message supplying content and channel/guild context.
            current: Clock value used when calculating cooldown state.

        Returns:
            The result of this operation.
        """
        bucket = self.get_bucket(message, current)
        return None if bucket is None else bucket.update_rate_limit(current)


class MaxConcurrency:
    """Max Concurrency data and behaviour.

    Attributes:
        number: Maximum concurrent command invocations allowed for a bucket.
        per: Length of the local cooldown interval in seconds.
        wait: Whether to return the created webhook message instead of an empty response.
    """

    def __init__(
        self, number: int, per: BucketType = BucketType.default, *, wait: bool = False
    ) -> None:
        """Initialize the max concurrency with the supplied configuration.

        Args:
            number: Maximum concurrent command invocations allowed for a bucket.
            per: Length of the local cooldown interval in seconds.
            wait: Whether to return the created webhook message instead of an empty response.
        """
        self.number: int = number
        self.per: BucketType = per
        self.wait: bool = wait
        self._mapping: dict[Any, asyncio.Semaphore] = {}

    def copy(self) -> "MaxConcurrency":
        """Copy.

        Returns:
            The result of this operation.
        """
        return MaxConcurrency(self.number, self.per, wait=self.wait)

    def get_key(self, message: Any) -> Any:
        """Derive the command bucket key from its invocation context.

        Args:
            message: Message supplying content and channel/guild context.

        Returns:
            The requested key.
        """
        return self.per.get_key(message)

    async def acquire(self, message: Any) -> None:
        """Acquire.

        Args:
            message: Message supplying content and channel/guild context.

        Returns:
            None.
        """
        key = self.get_key(message)
        sem = self._mapping.setdefault(key, asyncio.Semaphore(self.number))
        if not self.wait and sem.locked():
            from .errors import MaxConcurrencyReached

            raise MaxConcurrencyReached("Maximum concurrency reached")
        await sem.acquire()

    async def release(self, message: Any) -> None:
        """Release.

        Args:
            message: Message supplying content and channel/guild context.

        Returns:
            None.
        """
        key = self.get_key(message)
        sem = self._mapping.get(key)
        if sem is not None:
            sem.release()


__all__ = ("BucketType", "Cooldown", "CooldownMapping", "MaxConcurrency")
