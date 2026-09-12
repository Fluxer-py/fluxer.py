"""Resolve service URLs used by the existing REST, Gateway and asset APIs.

Discovery is unauthenticated and never derives auxiliary hosts from an API URL.
An explicit REST override can operate without discovery; auxiliary service URLs
then require an instance origin to have been configured separately.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import aiohttp

__all__: tuple[str, ...] = ()


class Endpoints:
    """Keep discovered bases and the caller's optional REST override.

    Attributes:
        api: Return an already-versioned REST base.
    """

    def __init__(self, instance_url: str | None, api_url: str | None) -> None:
        """Initialize the endpoints with the supplied configuration.

        Args:
            instance_url: Origin publishing the unauthenticated Fluxer discovery document.
            api_url: Already-versioned REST service override, including any instance path prefix.
        """
        self._origin = instance_url or (
            "https://fluxer.app" if api_url is None else None
        )
        self._override = api_url.rstrip("/") if api_url else None
        if self._override is not None:
            parts = urlsplit(self._override)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.netloc
                or parts.username
                or parts.password
                or parts.query
                or parts.fragment
            ):
                raise ValueError(
                    "api_url must be an absolute HTTP base without credentials, query, or fragment"
                )
        self._values: dict[str, str] = {}
        self._ready = False
        self._lock = asyncio.Lock()

    async def initialize(self, session: aiohttp.ClientSession) -> None:
        """Read discovery once, allowing a later retry after a failed request.

        Args:
            session: Session used by this operation.

        Returns:
            None.
        """
        async with self._lock:
            if self._ready:
                return
            if self._origin is not None:
                parsed = urlsplit(self._origin)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.netloc
                    or parsed.username
                    or parsed.password
                ):
                    raise ValueError("instance_url must be an absolute HTTP origin")
                url = f"{parsed.scheme}://{parsed.netloc}/.well-known/fluxer"
                async with session.get(url) as response:
                    response.raise_for_status()
                    document = await response.json()
                values = (
                    document.get("endpoints") if isinstance(document, dict) else None
                )
                if not isinstance(values, dict):
                    raise ValueError("Instance discovery has no endpoints object")
                for name in (
                    "api_public",
                    "gateway",
                    "media",
                    "static_cdn",
                    "invite",
                    "webapp",
                ):
                    value = values.get(name)
                    if not isinstance(value, str):
                        raise ValueError(f"Instance discovery has no {name} URL")
                    parts = urlsplit(value)
                    schemes = {"ws", "wss"} if name == "gateway" else {"http", "https"}
                    if (
                        parts.scheme not in schemes
                        or not parts.netloc
                        or parts.username
                        or parts.password
                    ):
                        raise ValueError(
                            f"Instance discovery has an invalid {name} URL"
                        )
                self._values = dict(values)
            self._ready = True

    @property
    def api(self) -> str:
        """Return an already-versioned REST base.

        Returns:
            The result of this operation.
        """
        if self._override is not None:
            return self._override
        return self.base("api_public").rstrip("/") + "/v1"

    def base(self, name: str) -> str:
        """Return a published base or explain the missing configuration.

        Args:
            name: Name to assign or resolve in this operation.

        Returns:
            The result of this operation.
        """
        try:
            return self._values[name]
        except KeyError:
            raise RuntimeError(
                f"The {name} endpoint is unavailable; configure instance_url and initialize the client"
            ) from None


def asset_url(http: object | None, service: str, path: str) -> str:
    """Construct an existing model URL using its client's discovered service.

    Args:
        http: Transport to bind for subsequent operations; None creates an unbound model.
        service: Service used by this operation.
        path: Filesystem path or operation path accepted by this method.

    Returns:
        The result of this operation.
    """
    endpoints = getattr(http, "_endpoints", None)
    if endpoints is None:
        raise RuntimeError("This URL requires an initialized client with instance_url")
    return endpoints.base(service).rstrip("/") + "/" + path.lstrip("/")
