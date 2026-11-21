"""Console logging setup used by ``Client.run`` and ``fluxer.utils.setup_logging``.

Matches discord.py's ``utils.setup_logging``: a coloured formatter when the
stream supports it, with optional ``rich`` output when the ``rich`` extra is
installed. Only standard-library modules are imported here so that any part of
the package can import it without a cycle.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from typing import Any

_LIBRARY_LOGGER = __name__.partition(".")[0]
_DEFAULT_TAG = "_fluxer_default_handler"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _is_docker() -> bool:
    path = "/proc/self/cgroup"
    if os.path.exists("/.dockerenv"):
        return True
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8", errors="ignore") as cgroup:
        return any("docker" in line for line in cgroup)


def stream_supports_colour(stream: Any) -> bool:
    """Return whether a stream can display ANSI colours.

    Args:
        stream: The stream a handler writes to, usually ``sys.stderr``.

    Returns:
        True for terminals that render ANSI colour codes. ``NO_COLOR`` in the
        environment always disables colour.
    """
    if "NO_COLOR" in os.environ:
        return False
    is_a_tty = hasattr(stream, "isatty") and stream.isatty()
    # PyCharm and VS Code render colour in their built-in terminals.
    if "PYCHARM_HOSTED" in os.environ or os.environ.get("TERM_PROGRAM") == "vscode":
        return is_a_tty
    if sys.platform != "win32":
        # Docker does not consistently attach a TTY.
        return is_a_tty or _is_docker()
    # ANSICON covers consoles such as ConEmu; WT_SESSION is Windows Terminal.
    return is_a_tty and ("ANSICON" in os.environ or "WT_SESSION" in os.environ)


class _ColourFormatter(logging.Formatter):
    """ANSI colour formatter: grey time, coloured level, magenta logger name."""

    LEVEL_COLOURS = (
        (logging.DEBUG, "\x1b[40;1m"),
        (logging.INFO, "\x1b[34;1m"),
        (logging.WARNING, "\x1b[33;1m"),
        (logging.ERROR, "\x1b[31m"),
        (logging.CRITICAL, "\x1b[41m"),
    )

    FORMATS = {
        level: logging.Formatter(
            f"\x1b[30;1m%(asctime)s\x1b[0m {colour}%(levelname)-8s\x1b[0m "
            "\x1b[35m%(name)s\x1b[0m %(message)s",
            _DATE_FORMAT,
        )
        for level, colour in LEVEL_COLOURS
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format a record with the colours of its level.

        Args:
            record: The record to format.

        Returns:
            The coloured log line, with tracebacks in red.
        """
        formatter = self.FORMATS.get(record.levelno, self.FORMATS[logging.DEBUG])
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f"\x1b[31m{text}\x1b[0m"
        output = formatter.format(record)
        # Drop the cached coloured traceback so other handlers format their own.
        record.exc_text = None
        return output


def _plain_formatter() -> logging.Formatter:
    return logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}", _DATE_FORMAT, style="{"
    )


def _rich_handler_class() -> Callable[..., logging.Handler] | None:
    try:
        # Optional extra, imported only when logging is set up.
        from rich.logging import RichHandler  # noqa: PLC0415
    except ImportError:
        return None
    return RichHandler


def _is_default(handler: logging.Handler) -> bool:
    return getattr(handler, _DEFAULT_TAG, False)


def _logging_configured() -> bool:
    """Return whether the application already installed its own handlers."""
    loggers = (logging.getLogger(), logging.getLogger(_LIBRARY_LOGGER))
    return any(
        not _is_default(handler) for logger in loggers for handler in logger.handlers
    )


def _remove_default_handlers() -> None:
    for logger in (logging.getLogger(), logging.getLogger(_LIBRARY_LOGGER)):
        for handler in tuple(logger.handlers):
            if _is_default(handler):
                logger.removeHandler(handler)
                handler.close()


def _default_handler(
    formatter: logging.Formatter | None, use_rich: bool | None
) -> tuple[logging.Handler, logging.Formatter]:
    rich_handler = _rich_handler_class() if use_rich is not False else None
    if use_rich is True and rich_handler is None:
        raise RuntimeError(
            'use_rich=True needs the rich extra: pip install "fluxer.py[rich]"'
        )
    stream_is_tty = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    if rich_handler is not None and (use_rich is True or stream_is_tty):
        handler = rich_handler(
            rich_tracebacks=True,
            # Locals would print the token held by start() and request().
            tracebacks_show_locals=False,
            markup=False,
            show_path=False,
            log_time_format=f"[{_DATE_FORMAT}]",
        )
        # RichHandler draws the time and level columns itself.
        return handler, formatter or logging.Formatter("%(name)s: %(message)s")
    handler = logging.StreamHandler()
    if formatter is None:
        formatter = (
            _ColourFormatter()
            if stream_supports_colour(handler.stream)
            else _plain_formatter()
        )
    return handler, formatter


def setup_logging(
    *,
    handler: logging.Handler | None = None,
    formatter: logging.Formatter | None = None,
    level: int | str = logging.INFO,
    root: bool = True,
    use_rich: bool | None = None,
) -> None:
    """Set up console logging, similar to ``logging.basicConfig``.

    Without a ``handler``, output goes to standard error: through ``rich`` when
    the ``rich`` extra is installed and standard error is a terminal, otherwise
    with ANSI colours when the stream supports them, otherwise as plain text.
    Calling it again replaces the handler it installed before instead of adding
    a second one. ``Client.run`` calls it for you.

    Args:
        handler: The handler to install. Defaults to a console handler.
        formatter: The formatter for the handler. Defaults to a coloured one, or
            to ``"%(name)s: %(message)s"`` for the rich handler.
        level: The level to set, such as ``logging.DEBUG`` or ``"DEBUG"``.
        root: Whether to configure the root logger, so your own loggers print too,
            rather than only the ``fluxer`` logger.
        use_rich: True to require rich, False to never use it, None to use it
            when it is installed and standard error is a terminal.

    Raises:
        RuntimeError: If ``use_rich=True`` and rich is not installed.
        TypeError: If both ``handler`` and ``use_rich=True`` are given.
    """
    if handler is not None and use_rich is True:
        raise TypeError("use_rich=True cannot be combined with a custom handler")
    _remove_default_handlers()
    if handler is None:
        handler, formatter = _default_handler(formatter, use_rich)
    elif formatter is None:
        formatter = (
            _ColourFormatter()
            if isinstance(handler, logging.StreamHandler)
            and stream_supports_colour(handler.stream)
            else _plain_formatter()
        )
    setattr(handler, _DEFAULT_TAG, True)
    handler.setFormatter(formatter)
    logger = logging.getLogger() if root else logging.getLogger(_LIBRARY_LOGGER)
    logger.setLevel(level.upper() if isinstance(level, str) else level)
    logger.addHandler(handler)


__all__ = ("setup_logging", "stream_supports_colour")
