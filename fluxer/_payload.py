"""Helpers for reading loosely shaped API payloads."""

from __future__ import annotations

from typing import Any


def maybe_int(value: Any) -> int | None:
    """Convert a value to int, returning None when it is missing or not numeric."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def unwrap(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Return the first nested dict found under any of keys, else data itself."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data
