"""Asynchronous webhook handles and retained adapter compatibility names.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from typing import Any

from .models.webhook import Webhook, WebhookMessage


class WebhookAdapter:
    """Compatibility placeholder; async Webhook methods own the implemented transport.

    Attributes:
        __dict__: Instance namespace retained for compatibility; no platform fields are defined.
    """

    pass


class AsyncWebhookAdapter(WebhookAdapter):
    """Compatibility adapter name without a separate adapter implementation.

    Attributes:
        __dict__: Instance namespace retained for compatibility; no platform fields are defined.
    """

    pass


class RequestsWebhookAdapter(WebhookAdapter):
    """Unsupported synchronous adapter retained for import compatibility.

    Construction raises RuntimeError; use the existing asynchronous webhook methods.

    Attributes:
        __dict__: Instance namespace retained for compatibility; no platform fields are defined.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the requests webhook adapter with the supplied configuration.

        Args:
            *args: Positional arguments forwarded to the wrapped callback.
            **kwargs: Additional options forwarded to the underlying operation.
        """
        raise RuntimeError(
            "Synchronous RequestsWebhookAdapter is unsupported; use async Webhook methods instead"
        )


__all__ = (
    "Webhook",
    "WebhookMessage",
    "WebhookAdapter",
    "AsyncWebhookAdapter",
    "RequestsWebhookAdapter",
)
