"""Factories for independent, transport-bound HTTP snapshots."""

from copy import deepcopy
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _snapshot(factory: Callable[..., T], data: Any, *args: Any, **kwargs: Any) -> T:
    """Parse owned payload data without touching live state."""
    return factory(deepcopy(data), *args, **kwargs)
