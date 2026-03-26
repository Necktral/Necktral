from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class LegacyRoutePolicy:
    prefix: str
    successor: str
    sunset: str = ""
    settings_attr: str = ""
    default_sunset: str = ""
    relation: str = "successor-version"

    def resolve_sunset(self) -> str:
        if self.settings_attr:
            value = str(getattr(settings, self.settings_attr, "") or "").strip()
            if value:
                return value
        return str(self.sunset or self.default_sunset).strip()


LEGACY_ROUTE_POLICIES: dict[str, LegacyRoutePolicy] = {
    "/api/accounting/reports/": LegacyRoutePolicy(
        prefix="/api/accounting/reports/",
        successor="/api/reporting/catalog/",
        settings_attr="REPORTING_LEGACY_ACCOUNTING_REPORTS_SUNSET",
        default_sunset="Mon, 22 Jun 2026 00:00:00 GMT",
    ),
    "/api/backend/estacion-servicios/": LegacyRoutePolicy(
        prefix="/api/backend/estacion-servicios/",
        successor="/api/fuel/",
        sunset="Mon, 18 May 2026 00:00:00 GMT",
    ),
    "/api/backend/fuel/": LegacyRoutePolicy(
        prefix="/api/backend/fuel/",
        successor="/api/fuel/",
        sunset="Mon, 18 May 2026 00:00:00 GMT",
    ),
    "/api/legacy/billing/": LegacyRoutePolicy(
        prefix="/api/legacy/billing/",
        successor="/api/billing/",
        sunset="Mon, 18 May 2026 00:00:00 GMT",
    ),
}


CANONICAL_ROUTE_PREFIXES: dict[str, str] = {
    "accounting": "/api/accounting/",
    "billing": "/api/billing/",
    "fuel": "/api/fuel/",
    "reporting": "/api/reporting/",
    "dashboard": "/api/backend/dashboard/",
}
