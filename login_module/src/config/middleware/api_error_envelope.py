from __future__ import annotations

import json

from django.http import JsonResponse

from config.error_envelope import build_error_envelope


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

        # No tocar streaming responses (poco probable en /api, pero seguro)
        if getattr(response, "streaming", False):
            return response

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code < 400:
            return response

        path = getattr(request, "path", "") or ""
        if not path.startswith("/api/"):
            return response

        # DRF Response: podemos operar sobre response.data
        if hasattr(response, "data"):
            data = getattr(response, "data", None)
            if isinstance(data, dict) and "error" in data:
                return response
            response.data = build_error_envelope(request=request, status_code=status_code, exc=None, details=data)
            if hasattr(response, "render"):
                try:
                    response.render()
                except Exception:
                    pass
            return response

        # Django JsonResponse / HttpResponse: operar sobre content.
        # Meta: para /api/*, siempre devolver el envelope contractual en errores.
        content_type = (response.get("Content-Type") or "").lower()

        raw = ""
        if getattr(response, "content", None):
            try:
                raw = response.content.decode("utf-8")
            except Exception:
                raw = ""

        data = None
        if "application/json" in content_type:
            try:
                data = json.loads(raw) if raw else None
            except Exception:
                # Si el backend devolvió JSON inválido, igual envelopamos (y conservamos el raw como detalle).
                data = {"detail": raw or "Solicitud inválida."}
        else:
            # Si no es JSON, intentamos conservar algo útil.
            data = {"detail": raw} if raw else None

        # Si ya viene envelopado, no modificar.
        if isinstance(data, dict) and "error" in data:
            return response

        envelope = build_error_envelope(request=request, status_code=status_code, exc=None, details=data)
        return JsonResponse(envelope, status=status_code, json_dumps_params={"ensure_ascii": False})
