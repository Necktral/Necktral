from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class CookieJwtCsrfMiddleware:
    """CSRF para modo cookie en JWT.

    Si AUTH_TOKEN_TRANSPORT=cookie, exige X-CSRF-Token == cookie CSRF
    para metodos mutables. Esto previene CSRF en modo cookies.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "AUTH_TOKEN_TRANSPORT", "header") != "cookie":
            return self.get_response(request)

        if request.method in SAFE_METHODS:
            return self.get_response(request)

        # Login se permite sin CSRF (todavia no hay cookie CSRF)
        if request.path.startswith("/api/auth/login"):
            return self.get_response(request)

        access = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS_NAME)
        refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)
        if not access and not refresh:
            return self.get_response(request)

        csrf_cookie = request.COOKIES.get(settings.AUTH_COOKIE_CSRF_NAME)
        csrf_header = request.headers.get("X-CSRF-Token") or request.headers.get("X-CSRFToken")

        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            request.error_code_override = "AUTH_CSRF_FAILED"
            request.audit_reason_code_override = "CSRF_FAILED"
            return JsonResponse({"detail": "CSRF token missing or invalid."}, status=403)

        return self.get_response(request)
