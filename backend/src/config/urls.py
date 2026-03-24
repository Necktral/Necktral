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
    path("api/backend/auth/", include("kernels.auth_kernel.urls")),
    path("api/backend/iam/", include("apps.modulos.iam.urls")),
    path("api/backend/org/", include("apps.modulos.org.urls")),
    path("api/backend/reports/", include("apps.modulos.reports.urls")),
    path("api/backend/rbac/", include("apps.modulos.rbac.urls")),
    path("api/backend/sync/", include("apps.modulos.sync_engine.urls")),
    path("api/backend/sync-hmac/", include("apps.modulos.sync.urls")),
    path("api/backend/audit/", include("apps.modulos.audit.urls")),
    path("api/backend/metrics/", include("apps.modulos.common.urls")),
    path("api/backend/hr/", include("apps.modulos.hr.urls")),
    path("api/backend/accounting/", include("apps.modulos.accounting.urls")),
    path("api/backend/dashboard/", include("apps.modulos.dashboard.urls")),
    path("api/backend/payments/", include("apps.modulos.payments.urls")),
    path("api/backend/cec/", include("apps.modulos.cec.urls")),
    path("api/backend/integration/", include("apps.modulos.integration.urls")),
    path("api/backend/fuel/", include("kernels.estacion_servicios.urls")),
    path("api/backend/inventory/", include("kernels.inventarios.urls")),
    path("api/backend/billing/", include("kernels.facturacion.urls")),
    path("api/backend/procurement/", include("kernels.compras.urls")),
    path("api/backend/retail/", include("apps.modulos.ventas_retail.urls")),
    # Legacy API aliases (temporales por compatibilidad)
    path("api/auth/", include("kernels.auth_kernel.urls")),
    path("api/iam/", include("apps.modulos.iam.urls")),
    path("api/org/", include("apps.modulos.org.urls")),
    path("api/rbac/", include("apps.modulos.rbac.urls")),
    path("api/sync/", include("apps.modulos.sync_engine.urls")),
    path("api/sync-hmac/", include("apps.modulos.sync.urls")),
    path("api/audit/", include("apps.modulos.audit.urls")),
    path("api/metrics/", include("apps.modulos.common.urls")),
    path("api/hr/", include("apps.modulos.hr.urls")),
    path("api/accounting/", include("apps.modulos.accounting.urls")),
    path("api/payments/", include("apps.modulos.payments.urls")),
    path("api/cec/", include("apps.modulos.cec.urls")),
    path("api/integration/", include("apps.modulos.integration.urls")),
    path("api/fuel/", include("kernels.estacion_servicios.urls")),
    path("api/inventory/", include("kernels.inventarios.urls")),
    path("api/billing/", include("kernels.facturacion.urls")),
    path("api/procurement/", include("kernels.compras.urls")),
    path("api/retail/", include("apps.modulos.ventas_retail.urls")),
    # Alias histórico de billing (v0) mantenido solo en legacy.
    path("api/billing/", include("kernels.facturacion.urls_legacy")),
]
