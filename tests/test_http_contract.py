"""Offline response, credential, and mutation contract tests."""

import asyncio
import json
from typing import cast
from collections.abc import Mapping
import aiohttp
from unittest.mock import AsyncMock

import pytest
from multidict import CIMultiDict

from fluxer.errors import BadRequest, HTTPException, RateLimited
from fluxer.http import HTTPClient, RateLimiter, Route


class Response:
    def __init__(self, status=200, body=None, *, raw=None, headers=None):
        self.status = status
        self.reason = "test response"
        self.raw = raw if raw is not None else json.dumps(body)
        self.headers = CIMultiDict(headers or {"content-type": "application/json"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def text(self):
        return self.raw


class Session:
    closed = False

    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def client(*responses, **kwargs):
    http = HTTPClient("test-secret", api_url="https://instance.test/api/v1", **kwargs)
    http._session = cast(aiohttp.ClientSession, Session(*responses))
    return http


@pytest.mark.asyncio
async def test_response_variants_and_credential_scope():
    http = client(
        Response(body={"id": "1"}),
        Response(raw="ok", headers={"content-type": "text/plain"}),
        Response(204, raw=""),
    )
    assert await http.get_current_user() == {"id": "1"}
    assert await http.execute_slack_webhook(1, "capability", {}) == "ok"
    assert (
        await http.request(Route("DELETE", "/item", base_url="https://other.test/v1"))
        is None
    )
    calls = cast(Session, http._session).calls
    assert calls[0][2]["headers"]["Authorization"] == "Bot test-secret"
    assert "Authorization" not in calls[1][2]["headers"]
    assert "Authorization" not in calls[2][2]["headers"]
    assert all(call[2]["allow_redirects"] is False for call in calls)


@pytest.mark.asyncio
async def test_invalid_success_json_is_not_replayed():
    http = client(Response(raw="invalid JSON"))
    with pytest.raises(ValueError):
        await http.send_message(1, content="once")
    assert len(cast(Session, http._session).calls) == 1
    assert not any(lock.locked() for lock in http._rate_limiter._locks.values())


@pytest.mark.asyncio
async def test_validation_error_retains_envelope():
    body = {
        "code": "INVALID_FORM_BODY",
        "message": "Localized",
        "errors": [{"path": "name", "code": "TOO_SHORT"}],
        "extra": 0,
    }
    http = client(Response(400, body))
    with pytest.raises(BadRequest) as caught:
        await http.get_current_user()
    assert caught.value.raw_data == body
    assert caught.value.errors == body["errors"]
    assert len(cast(Session, http._session).calls) == 1


@pytest.mark.asyncio
async def test_user_global_limit_invalidates_without_retry():
    http = client(
        Response(
            429,
            {
                "code": "RATE_LIMITED",
                "message": "revoked",
                "global": True,
                "retry_after": 0.001,
            },
        ),
        is_bot=False,
    )
    http.token = "flx_existing_session"
    with pytest.raises(RateLimited) as caught:
        await http.get_current_user()
    assert caught.value.session_invalidated
    assert caught.value.message == "revoked"
    assert len(cast(Session, http._session).calls) == 1


@pytest.mark.asyncio
async def test_cancellation_does_not_release_another_task_lock():
    limiter = RateLimiter()
    await limiter.acquire("resource")
    blocked = asyncio.create_task(limiter.acquire("resource"))
    await asyncio.sleep(0)
    blocked.cancel()
    with pytest.raises(asyncio.CancelledError):
        await blocked
    assert limiter._get_lock("resource").locked()
    limiter.release("resource", {})
    assert not limiter._get_lock("resource").locked()


@pytest.mark.asyncio
async def test_nullable_edits_routes_and_reaction_encoding():
    http = HTTPClient("test", api_url="https://instance.test/v1")
    http.request = AsyncMock(return_value={})
    await http.modify_guild_member(1, 2)
    assert http.request.call_args.kwargs["json"] == {}
    await http.modify_guild_member(1, 2, nick=None, channel_id=None)
    assert http.request.call_args.kwargs["json"] == {"nick": None, "channel_id": None}
    await http.get_pinned_messages(1, before="2026-01-01T00:00:00Z")
    assert http.request.call_args.args[0].path == "/channels/{channel_id}/messages/pins"
    await http.add_reaction(1, 2, "👍")
    assert http.request.call_args.args[0]._suffix.endswith("/%F0%9F%91%8D/@me")
    await http.delete_guild(1, password="proof")
    assert http.request.call_args.args[0].method == "POST"
    assert http.request.call_args.args[0].path == "/guilds/{guild_id}/delete"


@pytest.mark.asyncio
async def test_discovery_is_unauthenticated_and_preserves_service_prefixes():
    from fluxer._endpoints import Endpoints

    class DiscoveryResponse(Response):
        def raise_for_status(self):
            pass

        async def json(self):
            return {
                "endpoints": {
                    "api_public": "https://api.test/prefix",
                    "gateway": "wss://gateway.test/ws?route=1",
                    "media": "https://media.test/assets",
                    "static_cdn": "https://static.test",
                    "invite": "https://invite.test",
                    "webapp": "https://web.test",
                }
            }

    class DiscoverySession:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return DiscoveryResponse()

    endpoints = Endpoints("https://instance.test", None)
    session = DiscoverySession()
    await asyncio.gather(
        endpoints.initialize(cast(aiohttp.ClientSession, session)),
        endpoints.initialize(cast(aiohttp.ClientSession, session)),
    )
    assert session.calls == [("https://instance.test/.well-known/fluxer", {})]
    assert endpoints.api == "https://api.test/prefix/v1"
    assert endpoints.base("media") == "https://media.test/assets"


@pytest.mark.asyncio
async def test_multipart_retry_rebuilds_body_and_preserves_attachment_metadata():
    http = client(Response(429, {"retry_after": 0.001}), Response(body={"id": "1"}))
    await http.send_message(
        1,
        content="upload",
        files=[{"filename": "a.txt", "data": b"abc", "description": "caption"}],
    )
    bodies = [call[2]["data"] for call in cast(Session, http._session).calls]
    assert len(bodies) == 2 and bodies[0] is not bodies[1]
    for form in bodies:
        payload = json.loads(form._fields[0][2])
        assert payload["attachments"] == [
            {"id": 0, "filename": "a.txt", "description": "caption"}
        ]
        assert form._fields[1][2] == b"abc"


@pytest.mark.asyncio
async def test_bucket_metadata_is_resource_scoped_and_malformed_headers_unlock():
    limiter = RateLimiter()
    first = Route("GET", "/channels/{channel_id}/messages", channel_id=1).bucket
    second = Route("GET", "/channels/{channel_id}/messages", channel_id=2).bucket
    await limiter.acquire(first)
    limiter._deny(first, 0.001)
    limiter.release(first, {"X-RateLimit-Bucket": "shared"})
    await limiter.acquire(second)
    limiter.release(second, {"X-RateLimit-Bucket": "shared"})
    assert limiter._bucket_hashes[first] != limiter._bucket_hashes[second]
    assert limiter._reset_times[limiter._bucket_hashes[first]] > 0
    await limiter.acquire("malformed")
    with pytest.raises(AttributeError):
        limiter.release("malformed", cast(Mapping[str, str], {None: "invalid header"}))
    assert not limiter._get_lock("malformed").locked()


@pytest.mark.asyncio
async def test_retry_exhaustion_preserves_last_http_error():
    import aiohttp

    http = client(
        Response(503, {"code": "TEMPORARY", "message": "retry", "retry_after": 0.001}),
        max_retries=1,
    )
    request = cast(Session, http._session).request

    def send(method, url, **kwargs):
        if cast(Session, http._session).calls:
            raise aiohttp.ClientConnectionError("offline")
        return request(method, url, **kwargs)

    cast(Session, http._session).request = send
    with pytest.raises(HTTPException) as caught:
        await http.get_current_user()
    assert caught.value.status == 503
    assert caught.value.code == "TEMPORARY"
