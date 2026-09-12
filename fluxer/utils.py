"""Snowflake, formatting, embed, and module-discovery utilities.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

import os
import pkgutil
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, Literal

from .models.embed import Embed

# Fluxer snowflakes use the 2015-01-01T00:00:00Z epoch.
FLUXER_EPOCH = 1420070400000


def snowflake_to_datetime(snowflake: str | int) -> datetime:
    """Convert a Fluxer snowflake to its UTC creation time.

    The timestamp uses 41 bits above the 22 worker/process/sequence bits and
    is measured from the Fluxer epoch of 2015-01-01.

    Args:
        snowflake: Decimal snowflake whose timestamp should be decoded.

    Returns:
        A timezone-aware UTC datetime.
    """
    timestamp_ms = (int(snowflake) >> 22) + FLUXER_EPOCH
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def datetime_to_snowflake(dt: datetime) -> int:
    """Build the lowest snowflake for a timestamp, suitable for pagination.

    Args:
        dt: Timestamp to encode; naive datetimes follow the local timezone.

    Returns:
        A snowflake with all worker, process, and sequence bits cleared.
    """
    timestamp_ms = int(dt.timestamp() * 1000)
    snowflake = (timestamp_ms - FLUXER_EPOCH) << 22
    return snowflake


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    Returns:
        The current time with UTC timezone information.
    """
    return datetime.now(timezone.utc)


_MARKDOWN_ESCAPE_SUBREGEX = "|".join(
    rf"\{c}(?=([\s\S]*((?<!\{c})\{c})))" for c in ("*", "`", "_", "~", "|")
)

_MARKDOWN_ESCAPE_COMMON = r"^>(?:>>)?\s|\[.+\]\(.+\)"

_MARKDOWN_ESCAPE_REGEX = re.compile(
    rf"(?P<markdown>{_MARKDOWN_ESCAPE_SUBREGEX}|{_MARKDOWN_ESCAPE_COMMON})",
    re.MULTILINE,
)

_URL_REGEX = r"(?P<url><[^: >]+:\/[^ >]+>|(?:https?|steam):\/\/[^\s<]+[^<.,:;\"\'\]\s])"

_MARKDOWN_STOCK_REGEX = rf"(?P<markdown>[_\\~|\*`]|{_MARKDOWN_ESCAPE_COMMON})"


def remove_markdown(text: str, *, ignore_links: bool = True) -> str:
    """Remove recognised Markdown punctuation from text.

    Args:
        text: Text whose Markdown punctuation should be removed.
        ignore_links: Preserve punctuation inside recognised links when true.

    Returns:
        Text with matching punctuation removed.

    Note:
        This is a pattern-based transformation, not a Markdown parser. It can
        also remove punctuation that was intended as ordinary text.
    """

    def replacement(match: re.Match[str]) -> str:
        groupdict = match.groupdict()
        return groupdict.get("url", "")

    regex = _MARKDOWN_STOCK_REGEX
    if ignore_links:
        regex = f"(?:{_URL_REGEX}|{regex})"
    return re.sub(regex, replacement, text, flags=re.MULTILINE)


def escape_markdown(
    text: str, *, as_needed: bool = False, ignore_links: bool = True
) -> str:
    """Escape recognised Markdown punctuation for literal display.

    Args:
        text: Text to protect from Markdown formatting.
        as_needed: Escape paired formatting delimiters only where required.
        ignore_links: Preserve recognised links when escaping all punctuation.

    Returns:
        Text containing backslash escapes for matching punctuation.
    """
    if not as_needed:

        def replacement(match: re.Match[str]) -> str:
            groupdict = match.groupdict()
            is_url = groupdict.get("url")
            if is_url:
                return is_url
            return "\\" + groupdict["markdown"]

        regex = _MARKDOWN_STOCK_REGEX
        if ignore_links:
            regex = f"(?:{_URL_REGEX}|{regex})"
        return re.sub(regex, replacement, text, flags=re.MULTILINE)
    else:
        text = re.sub(r"\\", r"\\\\", text)
        return _MARKDOWN_ESCAPE_REGEX.sub(r"\\\1", text)


TimestampStyle = Literal["t", "T", "d", "D", "f", "F", "s", "S", "R"]


def format_dt(dt: datetime | float, /, style: TimestampStyle = "f") -> str:
    """Format a timestamp using Fluxer's client-rendered timestamp notation.

    Args:
        dt: Datetime or Unix timestamp in seconds. Naive datetimes use local time.
        style: Display style: t/T for time, d/D for date, f/F for date and time,
            s/S for numeric date and time, or R for relative time.

    Returns:
        Timestamp markup rendered in each recipient's locale.

    Example:
        from fluxer.utils import format_dt, utcnow
        print(format_dt(utcnow(), style="R"))
    """
    if isinstance(dt, datetime):
        dt = dt.timestamp()
    return f"<t:{int(dt)}:{style}>"


def search_directory(path: str) -> Iterator[str]:
    """Yield importable module names below a directory in the working tree.

    Args:
        path: Directory below the current working directory to inspect.

    Yields:
        Dotted module names suitable for the existing extension loader.

    Raises:
        ValueError: The path is outside the working directory, missing, or not a directory.
    """
    relpath = os.path.relpath(path)  # relative and normalized
    if ".." in relpath:
        msg = "Modules outside the cwd require a package to be specified"
        raise ValueError(msg)

    abspath = os.path.abspath(path)
    if not os.path.exists(relpath):
        msg = f"Provided path '{abspath}' does not exist"
        raise ValueError(msg)
    if not os.path.isdir(relpath):
        msg = f"Provided path '{abspath}' is not a directory"
        raise ValueError(msg)

    prefix = relpath.replace(os.sep, ".")
    if prefix in ("", "."):
        prefix = ""
    else:
        prefix += "."

    for _, name, ispkg in pkgutil.iter_modules([path]):
        if ispkg:
            yield from search_directory(os.path.join(path, name))
        else:
            yield prefix + name


def process_embed_args(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Normalize singular and plural embed arguments for message requests.

    Args:
        kwargs: Message options modified in place; a supplied singular embed
            takes precedence over the plural embeds option.

    Returns:
        The same options mapping with rich-embed request dictionaries.

    Note:
        Parsed Embed objects retain response metadata, but this conversion
        omits fields that the server does not accept in rich-embed input.
    """
    # Handle singular 'embed' parameter
    if "embed" in kwargs:
        embed = kwargs.pop("embed")
        if embed is not None:
            # Convert Embed object to dict
            if isinstance(embed, Embed):
                kwargs["embeds"] = [embed._to_request_dict()]
            else:
                # Assume it's already a dict
                kwargs["embeds"] = [embed]

    # Handle plural 'embeds' parameter - convert any Embed objects to dicts
    if "embeds" in kwargs and kwargs["embeds"] is not None:
        kwargs["embeds"] = [
            e._to_request_dict() if isinstance(e, Embed) else e
            for e in kwargs["embeds"]
        ]

    return kwargs


def escape_mentions(text: str) -> str:
    """Prevent supported user, role, everyone, and here mentions from notifying.

    Args:
        text: Text containing mention syntax to neutralize.

    Returns:
        Text with a zero-width character inserted in matching mentions.

    Note:
        Channel mentions are preserved.
    """
    return re.sub(r"@(everyone|here|[!&]?[0-9]{17,20})", "@\u200b\\1", text)


__all__ = (
    "snowflake_to_datetime",
    "datetime_to_snowflake",
    "utcnow",
    "remove_markdown",
    "escape_markdown",
    "format_dt",
    "search_directory",
    "process_embed_args",
    "escape_mentions",
    "FLUXER_EPOCH",
    "TimestampStyle",
)
