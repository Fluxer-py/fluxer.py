from __future__ import annotations

from .models.webhook import Webhook, WebhookMessage


class WebhookAdapter:
    pass


class AsyncWebhookAdapter(WebhookAdapter):
    pass


class RequestsWebhookAdapter(WebhookAdapter):
    def __init__(self, *args, **kwargs) -> None:
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
