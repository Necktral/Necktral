"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from config.csp_report import csp_report
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.permissions import BasePermission


class SchemaAccessPermission(BasePermission):
    def has_permission(self, request, view) -> bool:  # noqa: D401
        if bool(getattr(settings, "OPENAPI_ALLOW_ANON", False)):
            return True
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated)

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[SchemaAccessPermission]), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[SchemaAccessPermission]),
        name="swagger-ui",
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema", permission_classes=[SchemaAccessPermission]),
        name="redoc",
    ),
    # CSP reports (report-only)
    path("api/csp/report/", csp_report, name="csp-report"),
    # Backend v2 canonical (public)
    path("api/backend/auth/", include("modulos.auth_kernel.urls")),
    path("api/backend/iam/", include("apps.iam.urls")),
    path("api/backend/org/", include("apps.org.urls")),
    # Legacy API aliases (deprecated)
    path("api/auth/", include("modulos.auth_kernel.urls")),
    path("api/iam/", include("apps.iam.urls")),
    path("api/org/", include("apps.org.urls")),
    # RBAC
    path("api/rbac/", include("apps.rbac.urls")),
    path("api/sync/", include("apps.sync_engine.urls")),
    path("api/sync-hmac/", include("apps.sync.urls")),
    # Auditoría
    path("api/audit/", include("apps.audit.urls")),
    # Observabilidad
    path("api/metrics/", include("apps.common.urls")),
    # HR
    path("api/hr/", include("apps.hr.urls")),
    # Accounting
    path("api/accounting/", include("apps.accounting.urls")),
    # Payments/Cash
    path("api/payments/", include("apps.payments.urls")),
    # CEC
    path("api/cec/", include("apps.cec.urls")),
    # Integration Backbone
    path("api/integration/", include("apps.integration.urls")),
    # Reportes
    path("api/reports/", include("apps.reports.urls")),
    # Estación de Servicios
    path("api/fuel/", include("modulos.estacion_servicios.urls")),
]

urlpatterns += [
    path("api/inventory/", include("modulos.inventarios.urls")),
    path("api/billing/", include("modulos.facturacion.urls")),
    path("api/procurement/", include("modulos.compras.urls")),
]

urlpatterns += [
    path("api/billing/", include("modulos.facturacion.urls_legacy")),
]
