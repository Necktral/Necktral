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

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.defaults import page_not_found, server_error
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from config.error_envelope import build_error_envelope


def api_handler404(request, exception, template_name="404.html"):
    path_ = getattr(request, "path", "") or ""
    if path_.startswith("/api/"):
        envelope = build_error_envelope(
            request=request,
            status_code=404,
            exc=None,
            details={"detail": "No encontrado."},
        )
        return JsonResponse(envelope, status=404, json_dumps_params={"ensure_ascii": False})
    return page_not_found(request, exception, template_name=template_name)


def api_handler500(request, template_name="500.html"):
    path_ = getattr(request, "path", "") or ""
    if path_.startswith("/api/"):
        envelope = build_error_envelope(
            request=request,
            status_code=500,
            exc=None,
            details={"detail": "Error interno."},
        )
        return JsonResponse(envelope, status=500, json_dumps_params={"ensure_ascii": False})
    return server_error(request, template_name=template_name)


handler404 = api_handler404
handler500 = api_handler500

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Auth
    path("api/auth/", include("apps.accounts.urls")),
    # IAM
    path("api/iam/", include("apps.iam.urls")),
    # RBAC
    path("api/rbac/", include("apps.rbac.urls")),
    path("api/sync/", include("apps.sync_engine.urls")),
    path("api/sync-hmac/", include("apps.sync.urls")),
    # Auditoría
    path("api/audit/", include("apps.audit.urls")),
    # ORG
    path("api/org/", include("apps.org.urls")),
    # HR
    path("api/hr/", include("apps.hr.urls")),
    # Estación de Servicios
    path("api/fuel/", include("modulos.estacion_servicios.urls")),
]

urlpatterns += [
    path("api/inventory/", include("modulos.inventarios.urls")),
    path("api/billing/", include("modulos.facturacion.urls")),
]

urlpatterns += [
    path("api/billing/", include("modulos.facturacion.urls_legacy")),
]
