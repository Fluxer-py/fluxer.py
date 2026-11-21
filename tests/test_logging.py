"""Console logging setup, Client.run integration, and secret-free HTTP logs."""

import asyncio
import io
import logging
import sys
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest

import fluxer
from fluxer import _logging
from fluxer.http import HTTPClient, Route
from fluxer.utils import setup_logging, stream_supports_colour


class FakeTTY(io.StringIO):
    def __init__(self, tty: bool = True) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture(autouse=True)
def restore_loggers() -> Iterator[None]:
    loggers = (logging.getLogger(), logging.getLogger("fluxer"))
    saved = [(logger, list(logger.handlers), logger.level) for logger in loggers]
    yield
    for logger, handlers, level in saved:
        for handler in list(logger.handlers):
            if handler not in handlers:
                logger.removeHandler(handler)
        logger.setLevel(level)


def installed(logger_name: str | None = None) -> list[logging.Handler]:
    logger = logging.getLogger(logger_name)
    return [h for h in logger.handlers if getattr(h, "_fluxer_default_handler", False)]


def test_colour_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("NO_COLOR", "PYCHARM_HOSTED", "TERM_PROGRAM", "WT_SESSION", "ANSICON"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(_logging, "_is_docker", lambda: False)

    monkeypatch.setattr(sys, "platform", "linux")
    assert stream_supports_colour(FakeTTY(True))
    assert not stream_supports_colour(FakeTTY(False))
    monkeypatch.setattr(_logging, "_is_docker", lambda: True)
    assert stream_supports_colour(FakeTTY(False))

    monkeypatch.setattr(sys, "platform", "win32")
    assert not stream_supports_colour(FakeTTY(True))
    monkeypatch.setenv("WT_SESSION", "1")
    assert stream_supports_colour(FakeTTY(True))
    monkeypatch.setenv("NO_COLOR", "1")
    assert not stream_supports_colour(FakeTTY(True))

    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    assert stream_supports_colour(FakeTTY(True))
    assert not stream_supports_colour(object())


def test_colour_formatter_output() -> None:
    record = logging.LogRecord(
        "fluxer.http", logging.WARNING, "x", 1, "hi %s", ("there",), None
    )
    text = _logging._ColourFormatter().format(record)
    assert (
        "\x1b[33;1mWARNING" in text
        and "fluxer.http" in text
        and text.endswith("hi there")
    )


def test_without_rich_falls_back_to_ansi_or_plain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "rich.logging", None)
    monkeypatch.setattr(_logging, "stream_supports_colour", lambda stream: True)
    setup_logging()
    (handler,) = installed()
    assert type(handler) is logging.StreamHandler
    assert isinstance(handler.formatter, _logging._ColourFormatter)

    monkeypatch.setattr(_logging, "stream_supports_colour", lambda stream: False)
    setup_logging()
    (handler,) = installed()
    assert not isinstance(handler.formatter, _logging._ColourFormatter)

    with pytest.raises(RuntimeError, match="rich extra"):
        setup_logging(use_rich=True)
    with pytest.raises(TypeError):
        setup_logging(handler=logging.StreamHandler(), use_rich=True)


def test_rich_is_used_on_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    rich_logging = pytest.importorskip("rich.logging")
    monkeypatch.setattr(sys, "stderr", FakeTTY(True))
    setup_logging(level="DEBUG")
    (installed_handler,) = installed()
    assert isinstance(installed_handler, rich_logging.RichHandler)
    handler: Any = installed_handler
    assert handler.rich_tracebacks and not handler.markup
    assert handler.tracebacks_show_locals is False
    assert logging.getLogger().level == logging.DEBUG

    monkeypatch.setattr(sys, "stderr", FakeTTY(False))
    setup_logging()
    assert not isinstance(installed()[0], rich_logging.RichHandler)
    setup_logging(use_rich=False)
    assert not isinstance(installed()[0], rich_logging.RichHandler)
    setup_logging(use_rich=True)
    assert isinstance(installed()[0], rich_logging.RichHandler)


def test_repeated_setup_replaces_instead_of_stacking() -> None:
    setup_logging()
    setup_logging()
    assert len(installed()) == 1 and not installed("fluxer")
    setup_logging(root=False, level=logging.WARNING)
    assert not installed() and len(installed("fluxer")) == 1
    assert logging.getLogger("fluxer").level == logging.WARNING
    custom = logging.StreamHandler(FakeTTY(False))
    custom_formatter = logging.Formatter("%(message)s")
    setup_logging(handler=custom, formatter=custom_formatter, root=False)
    assert installed("fluxer") == [custom] and custom.formatter is custom_formatter


def run_without_connecting(
    client: fluxer.Client, monkeypatch: pytest.MonkeyPatch, **kwargs: Any
) -> None:
    monkeypatch.setattr(client, "start", AsyncMock())
    monkeypatch.setattr(client, "close", AsyncMock())
    client.run("token", **kwargs)


def test_run_sets_up_logging_like_setup_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_logging, "_logging_configured", lambda: False)
    monkeypatch.setattr(fluxer.client, "_logging_configured", lambda: False)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(fluxer.client, "setup_logging", lambda **kw: calls.append(kw))

    run_without_connecting(fluxer.Client(), monkeypatch)
    assert calls[-1] == {
        "handler": None,
        "formatter": None,
        "level": logging.INFO,
        "root": False,
        "use_rich": None,
    }
    handler = logging.NullHandler()
    formatter = logging.Formatter("%(message)s")
    run_without_connecting(
        fluxer.Client(),
        monkeypatch,
        log_handler=handler,
        log_formatter=formatter,
        log_level="DEBUG",
        root_logger=True,
        use_rich=False,
    )
    assert calls[-1] == {
        "handler": handler,
        "formatter": formatter,
        "level": "DEBUG",
        "root": True,
        "use_rich": False,
    }
    calls.clear()
    run_without_connecting(fluxer.Client(), monkeypatch, log_handler=None)
    assert calls == []


def test_run_respects_existing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    foreign = logging.StreamHandler(FakeTTY(False))
    logging.getLogger().addHandler(foreign)
    run_without_connecting(fluxer.Client(), monkeypatch, log_level=logging.DEBUG)
    assert not installed() and not installed("fluxer")
    assert logging.getLogger("fluxer").level == logging.DEBUG

    # An explicit handler is always installed, and repeated runs don't stack it.
    explicit = logging.NullHandler()
    run_without_connecting(fluxer.Client(), monkeypatch, log_handler=explicit)
    run_without_connecting(fluxer.Client(), monkeypatch, log_handler=explicit)
    assert installed("fluxer") == [explicit]


class FakeResponse:
    def __init__(self, status: int, body: str, headers: dict[str, str]) -> None:
        self.status = status
        self.reason = "reason"
        self._body = body
        self.headers = {"Content-Type": "application/json", **headers}

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def text(self) -> str:
        return self._body


class FakeSession:
    closed = False

    def __init__(self) -> None:
        self.calls = 0

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls == 1:
            return FakeResponse(
                429,
                '{"code":"RATE_LIMITED","message":"slow","retry_after":0.01,"global":false}',
                {"X-RateLimit-Bucket": "abc"},
            )
        if self.calls == 2:
            return FakeResponse(503, '{"code":"UNAVAILABLE","message":"down"}', {})
        if self.calls == 3:
            raise aiohttp.ClientConnectionError(f"cannot reach {url}")
        return FakeResponse(200, '{"id":"1","token":"SECRET"}', {})

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_http_logs_rate_limits_without_urls_or_tokens(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    http = HTTPClient("BOT_TOKEN", api_url="https://instance.test/v1")
    session = FakeSession()
    monkeypatch.setattr(http, "_session", session)
    monkeypatch.setattr(http, "_ensure_session", AsyncMock(return_value=session))
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda delay: real_sleep(0))
    route = Route(
        "POST",
        "/webhooks/{webhook_id}/{token}",
        base_url="https://instance.test/v1",
        webhook_id=5,
        token="SECRET",
    )
    with caplog.at_level(logging.DEBUG, logger="fluxer"):
        result = await http.request(route, json={"content": "hi"})
    assert result == {"id": "1", "token": "SECRET"}
    messages = [record.getMessage() for record in caplog.records]
    assert any("responded with 429" in message for message in messages)
    assert any("returned 503, retrying" in message for message in messages)
    assert any("ClientConnectionError" in message for message in messages)
    assert any("has returned 200" in message for message in messages)
    assert any("initial rate limit bucket hash" in message for message in messages)
    for message in messages:
        assert "SECRET" not in message and "BOT_TOKEN" not in message
        assert "https://" not in message
