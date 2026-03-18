from __future__ import annotations

import json

from config.error_envelope import build_error_envelope


def _is_error_envelope(data) -> bool:
    if not isinstance(data, dict):
        return False
    err = data.get("error")
    if not isinstance(err, dict):
        return False
    required = {"code", "http_status", "message", "details", "request_id", "timestamp", "retryable"}
    return required.issubset(err.keys())


class ApiErrorEnvelopeMiddleware:
    """Normaliza errores JSON al envelope contractual.

    Cubre casos donde el código retorna manualmente:
    - JsonResponse({"detail": ...}, status=4xx)
    - Response({"detail": ...}, status=4xx)

    No toca respuestas no-JSON.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code < 400:
            return response

        path = getattr(request, "path", "") or ""
        if not path.startswith("/api/"):
            return response

        # DRF Response: podemos operar sobre response.data
        if hasattr(response, "data"):
            data = getattr(response, "data", None)
            if _is_error_envelope(data):
                return response
            response.data = build_error_envelope(request=request, status_code=status_code, exc=None, details=data)
            if hasattr(response, "render"):
                try:
                    response.render()
                except Exception:
                    pass
            return response

        # Django JsonResponse / HttpResponse JSON: operar sobre content
        content_type = (response.get("Content-Type") or "").lower()
        if "application/json" not in content_type:
            return response

        try:
            raw = response.content.decode("utf-8") if getattr(response, "content", None) else ""
            data = json.loads(raw) if raw else None
        except Exception:
            return response

        if _is_error_envelope(data):
            return response

        envelope = build_error_envelope(request=request, status_code=status_code, exc=None, details=data)
        response.content = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        return response
