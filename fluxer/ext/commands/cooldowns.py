from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any


class BucketType(Enum):
    default = 0
    user = 1
    guild = 2
    channel = 3
    member = 4

    def get_key(self, message: Any) -> Any:
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
    def __init__(
        self, rate: int, per: float, type: BucketType = BucketType.default
    ) -> None:
        self.rate = int(rate)
        self.per = float(per)
        self.type = type
        self._tokens = self.rate
        self._window = 0.0
        self._last = 0.0

    def copy(self) -> "Cooldown":
        return Cooldown(self.rate, self.per, self.type)

    def get_tokens(self, current: float | None = None) -> int:
        current = current or time.time()
        if current > self._window + self.per:
            return self.rate
        return self._tokens

    def get_retry_after(self, current: float | None = None) -> float:
        current = current or time.time()
        tokens = self.get_tokens(current)
        if tokens == 0:
            return max(self.per - (current - self._window), 0.0)
        return 0.0

    def update_rate_limit(self, current: float | None = None) -> float | None:
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
        self._tokens = self.rate
        self._last = 0.0


class CooldownMapping:
    def __init__(self, original: Cooldown | None) -> None:
        self._cooldown = original
        self._cache: dict[Any, Cooldown] = {}

    @classmethod
    def from_cooldown(
        cls, rate: int, per: float, type: BucketType
    ) -> "CooldownMapping":
        return cls(Cooldown(rate, per, type))

    def copy(self) -> "CooldownMapping":
        return CooldownMapping(self._cooldown.copy() if self._cooldown else None)

    def get_bucket(self, message: Any, current: float | None = None) -> Cooldown | None:
        if self._cooldown is None:
            return None
        key = self._cooldown.type.get_key(message)
        if key not in self._cache:
            self._cache[key] = self._cooldown.copy()
        return self._cache[key]

    def update_rate_limit(
        self, message: Any, current: float | None = None
    ) -> float | None:
        bucket = self.get_bucket(message, current)
        return None if bucket is None else bucket.update_rate_limit(current)


class MaxConcurrency:
    def __init__(
        self, number: int, per: BucketType = BucketType.default, *, wait: bool = False
    ) -> None:
        self.number = number
        self.per = per
        self.wait = wait
        self._mapping: dict[Any, asyncio.Semaphore] = {}

    def copy(self) -> "MaxConcurrency":
        return MaxConcurrency(self.number, self.per, wait=self.wait)

    def get_key(self, message: Any) -> Any:
        return self.per.get_key(message)

    async def acquire(self, message: Any) -> None:
        key = self.get_key(message)
        sem = self._mapping.setdefault(key, asyncio.Semaphore(self.number))
        if not self.wait and sem.locked():
            from .errors import MaxConcurrencyReached

            raise MaxConcurrencyReached("Maximum concurrency reached")
        await sem.acquire()

    async def release(self, message: Any) -> None:
        key = self.get_key(message)
        sem = self._mapping.get(key)
        if sem is not None:
            sem.release()
