from __future__ import annotations

from config.routing_policy import LEGACY_ROUTE_POLICIES


class LegacyApiDeprecationMiddleware:
    """Inject deprecation headers for declared legacy public API prefixes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, "path", "") or ""
        matched_policy = next((policy for prefix, policy in LEGACY_ROUTE_POLICIES.items() if path.startswith(prefix)), None)
        if matched_policy:
            setattr(request, "_legacy_api_prefix", matched_policy.prefix)
        response = self.get_response(request)
        if matched_policy:
            if "Deprecation" not in response:
                response["Deprecation"] = "true"
            if "Sunset" not in response:
                response["Sunset"] = matched_policy.resolve_sunset()
            if "Link" not in response:
                response["Link"] = f'<{matched_policy.successor}>; rel="{matched_policy.relation}"'
        return response
