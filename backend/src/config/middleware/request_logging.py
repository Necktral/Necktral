from __future__ import annotations

import logging
import time

from config.metrics import record_request


class RequestLoggingMiddleware:
    """Log de inicio/fin para /api con request_id y duración."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("apps.observability")

    def __call__(self, request):
        path = getattr(request, "path", "") or ""
        if not path.startswith("/api/"):
            return self.get_response(request)

        start = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = int((time.monotonic() - start) * 1000)
            self._log(request, status_code=500, duration_ms=duration_ms, is_error=True)
            record_request(request, status_code=500, duration_ms=duration_ms)
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        self._log(request, status_code=getattr(response, "status_code", None), duration_ms=duration_ms)
        record_request(request, status_code=getattr(response, "status_code", None), duration_ms=duration_ms)
        return response

    def _log(self, request, *, status_code: int | None, duration_ms: int, is_error: bool = False) -> None:
        user = getattr(request, "user", None)
        actor_type = None
        actor_id = None
        if user is not None and getattr(user, "is_authenticated", False):
            actor_type = "USER"
            actor_id = str(getattr(user, "id", ""))

        extra = {
            "path": getattr(request, "path", "") or "",
            "method": getattr(request, "method", "") or "",
            "status_code": int(status_code) if status_code is not None else None,
            "duration_ms": duration_ms,
            "actor_type": actor_type,
            "actor_id": actor_id,
        }
        if is_error:
            self.logger.exception("api_request_failed", extra=extra)
        else:
            self.logger.info("api_request", extra=extra)
