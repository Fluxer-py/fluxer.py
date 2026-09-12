"""Exceptions retaining Fluxer HTTP and Gateway failure details.

The names below expose the package's existing supported behaviour.
"""

from __future__ import annotations

from typing import Any


class FluxerException(Exception):
    """Base exception for all fluxer.py errors.

    Attributes:
        args: Exception arguments retained by Python.
    """


# =============================================================================
# HTTP Errors
# =============================================================================


class HTTPException(FluxerException):
    """Raised when an HTTP request to the Fluxer API fails.

    Attributes:
        args: Exception arguments retained by Python.
        status: HTTP response status code.
        code: Stable machine-readable failure code.
        message: Localized server failure description.
        errors: Validation or conversion failures retained for caller inspection.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        errors: list[dict[str, Any]] | None = None,
        *,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the httpexception with the supplied configuration.

        Args:
            status: HTTP response status code.
            code: Stable machine-readable server failure code.
            message: Localized server-provided failure description.
            errors: Validation or conversion failures retained for caller inspection.
            raw_data: Original response envelope retained for fields outside the typed view.
        """
        self.status: int = status
        self.code: str = code
        self.message: str = message
        self.errors: list[dict[str, Any]] = errors if errors is not None else []
        self.raw_data: dict[str, Any] = dict(raw_data or {})

        rendered = f"{status} {code}: {message}"
        if self.errors:
            details = []
            for error in self.errors:
                path = str(error.get("path", "root"))
                error_code = error.get("code")
                error_message = error.get("message")
                detail = f"{path}: {error_code}" if error_code else path
                if error_message:
                    detail += f" - {error_message}"
                details.append(detail)
            rendered += f" [{'; '.join(details)}]"

        super().__init__(rendered)


class BadRequest(HTTPException):
    """400 Bad Request — invalid input.

    Attributes:
        args: Exception arguments retained by Python.
        status: HTTP response status code.
        code: Stable machine-readable failure code.
        message: Localized server failure description.
        errors: Validation or conversion failures retained for caller inspection.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """


class Unauthorized(HTTPException):
    """401 Unauthorized — bad or missing token.

    Attributes:
        args: Exception arguments retained by Python.
        status: HTTP response status code.
        code: Stable machine-readable failure code.
        message: Localized server failure description.
        errors: Validation or conversion failures retained for caller inspection.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """


class Forbidden(HTTPException):
    """403 Forbidden — missing permissions.

    Attributes:
        args: Exception arguments retained by Python.
        status: HTTP response status code.
        code: Stable machine-readable failure code.
        message: Localized server failure description.
        errors: Validation or conversion failures retained for caller inspection.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """


class NotFound(HTTPException):
    """404 Not Found — resource doesn't exist.

    Attributes:
        args: Exception arguments retained by Python.
        status: HTTP response status code.
        code: Stable machine-readable failure code.
        message: Localized server failure description.
        errors: Validation or conversion failures retained for caller inspection.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
    """


class RateLimited(HTTPException):
    """429 Too Many Requests — slow down.

    Attributes:
        args: Exception arguments retained by Python.
        status: HTTP response status code.
        code: Stable machine-readable failure code.
        message: Localized server failure description.
        errors: Validation or conversion failures retained for caller inspection.
        raw_data: Original payload retained for privacy-controlled, variant-specific, or unmodeled fields; excluded from repr.
        retry_after: Fractional seconds until the next request may be admitted.
        global_limit: Whether the denial applies to the account-wide allowance.
        session_invalidated: Session invalidated used by this operation.
    """

    def __init__(
        self,
        retry_after: float,
        *,
        code: str = "RATE_LIMITED",
        message: str = "Request rate limited",
        global_limit: bool = False,
        errors: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the rate limited with the supplied configuration.

        Args:
            retry_after: Fractional seconds until the next request may be admitted.
            code: Stable machine-readable server failure code.
            message: Localized server-provided failure description.
            global_limit: Whether the denial applies to the account-wide allowance.
            errors: Validation or conversion failures retained for caller inspection.
            **kwargs: Additional options forwarded to the underlying operation.
        """
        self.retry_after: float = retry_after
        self.global_limit: bool = global_limit
        self.session_invalidated: bool = False
        super().__init__(
            status=429,
            code=code,
            message=message,
            errors=errors,
            raw_data=kwargs.get("raw_data"),
        )


# =============================================================================
# Gateway Errors
# =============================================================================


class GatewayException(FluxerException):
    """Base for gateway/WebSocket errors.

    Attributes:
        args: Exception arguments retained by Python.
    """


class GatewayNotConnected(GatewayException):
    """Raised when trying to use the gateway before it's connected.

    Attributes:
        args: Exception arguments retained by Python.
    """


class ReconnectRequested(GatewayException):
    """The gateway has requested we reconnect.

    Attributes:
        args: Exception arguments retained by Python.
    """


class SessionInvalid(GatewayException):
    """The session is invalid and cannot be resumed.

    Attributes:
        args: Exception arguments retained by Python.
        resumable: Whether the Gateway permits resuming the previous session.
    """

    def __init__(self, resumable: bool = False) -> None:
        """Initialize the session invalid with the supplied configuration.

        Args:
            resumable: Whether the Gateway permits resuming the previous session.
        """
        self.resumable: bool = resumable
        super().__init__(f"Invalid session (resumable={resumable})")


# =============================================================================
# Client Errors
# =============================================================================


class LoginFailure(FluxerException):
    """Raised when the bot token is invalid.

    Attributes:
        args: Exception arguments retained by Python.
    """


# Map HTTP status codes to exception classes
_STATUS_MAP: dict[int, type[HTTPException]] = {
    400: BadRequest,
    401: Unauthorized,
    403: Forbidden,
    404: NotFound,
    429: RateLimited,
}


def http_exception_from_status(
    status: int, code: str, message: str, **kwargs: Any
) -> HTTPException:
    """Factory to create the right HTTPException subclass for a status code.

    Args:
        status: HTTP response status code.
        code: Stable machine-readable server failure code.
        message: Localized server-provided failure description.
        **kwargs: Additional options forwarded to the underlying operation.

    Returns:
        The result of this operation.
    """
    cls = _STATUS_MAP.get(status, HTTPException)
    if cls is RateLimited:
        return RateLimited(code=code, message=message, **kwargs)
    return cls(
        status=status,
        code=code,
        message=message,
        errors=kwargs.get("errors"),
        raw_data=kwargs.get("raw_data"),
    )


__all__ = (
    "FluxerException",
    "HTTPException",
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "RateLimited",
    "GatewayException",
    "GatewayNotConnected",
    "ReconnectRequested",
    "SessionInvalid",
    "LoginFailure",
    "http_exception_from_status",
)
