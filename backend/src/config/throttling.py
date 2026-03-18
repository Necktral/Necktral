from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class DeviceScopedRateThrottle(ScopedRateThrottle):
    """Throttle por device_id si existe, fallback a IP."""

    def get_cache_key(self, request, view):
        scope = getattr(view, "throttle_scope", None)
        if not scope:
            return None

        device_id = (request.META.get("HTTP_X_DEVICE_ID") or "").strip()
        ident = device_id or self.get_ident(request)
        if not ident:
            return None

        return self.cache_format % {"scope": scope, "ident": ident}


class AuthLoginRateThrottle(SimpleRateThrottle):
    """Throttle específico para login: IP + username."""

    scope = "auth_login"

    def get_rate(self):
        from django.conf import settings
        from rest_framework.settings import api_settings

        rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {}) or {}
        rate = rates.get(self.scope)
        if rate:
            return rate
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view):
        ip = self.get_ident(request) or "noip"
        username = ""
        try:
            if isinstance(getattr(request, "data", None), dict):
                username = str(request.data.get("username", "")).strip().lower()
        except Exception:
            username = ""

        if not username:
            username = "anon"

        ident = f"{ip}:{username}"
        return self.cache_format % {"scope": self.scope, "ident": ident}
