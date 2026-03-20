from __future__ import annotations


class LegacyApiDeprecationMiddleware:
    """Inject deprecation headers for legacy public API prefixes."""

    LEGACY_PREFIXES = (
        "/api/auth/",
        "/api/iam/",
        "/api/org/",
        "/api/billing/",
        "/api/inventory/",
        "/api/procurement/",
        "/api/fuel/",
    )
    SUNSET_AT = "Sun, 17 May 2026 00:00:00 GMT"
    SUCCESSOR_BY_PREFIX = {
        "/api/auth/": "/api/backend/auth/",
        "/api/iam/": "/api/backend/iam/",
        "/api/org/": "/api/backend/org/",
        "/api/billing/": "/api/backend/billing/",
        "/api/inventory/": "/api/backend/inventory/",
        "/api/procurement/": "/api/backend/procurement/",
        "/api/fuel/": "/api/backend/fuel/",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = getattr(request, "path", "") or ""
        matched_prefix = next((prefix for prefix in self.LEGACY_PREFIXES if path.startswith(prefix)), None)
        if matched_prefix:
            if "Deprecation" not in response:
                response["Deprecation"] = "true"
            if "Sunset" not in response:
                response["Sunset"] = self.SUNSET_AT
            # Preserve endpoint-specific successor links from wrappers when present.
            if "Link" not in response:
                successor = self.SUCCESSOR_BY_PREFIX.get(matched_prefix, "/api/backend/")
                response["Link"] = f'<{successor}>; rel="successor-version"'
        return response
