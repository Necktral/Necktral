from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Typed domain exception with stable code/context for observability."""

    default_code = "DOMAIN_ERROR"
    default_retryable = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.code = str(code or self.default_code)
        self.context: dict[str, Any] = dict(context or {})
        self.retryable = self.default_retryable if retryable is None else bool(retryable)

    def as_payload(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code,
            "retryable": self.retryable,
            "context": dict(self.context),
        }


class IntegrationError(DomainError):
    default_code = "INTEGRATION_ERROR"


class RetryableError(IntegrationError):
    default_code = "RETRYABLE_ERROR"
    default_retryable = True
