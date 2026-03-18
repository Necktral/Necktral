from __future__ import annotations

import contextvars
import re
import uuid


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_request_id_var = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id_var.get() or ""


def _sanitize_request_id(raw: str) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    if not _REQUEST_ID_RE.match(cleaned):
        return ""
    return cleaned


class RequestIdMiddleware:
    """Genera/propaga X-Request-Id y lo expone en request.request_id.

    Contrato:
    - Si el cliente envía X-Request-Id válido, se respeta.
    - Si no existe o es inválido, se genera uno.
    - Siempre se devuelve X-Request-Id en la respuesta.
    """

    header_name = "X-Request-Id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(self.header_name)
        request_id = _sanitize_request_id(incoming or "") or uuid.uuid4().hex

        setattr(request, "request_id", request_id)
        token = _request_id_var.set(request_id)
        try:
            import sentry_sdk

            sentry_sdk.set_tag("request_id", request_id)
        except Exception:
            pass

        try:
            response = self.get_response(request)
        finally:
            _request_id_var.reset(token)

        try:
            response[self.header_name] = request_id
        except Exception:
            pass

        return response
