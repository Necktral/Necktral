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
from django.urls import include, path
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)
from rest_framework.permissions import AllowAny

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
    # Auditoría
    path("api/audit/", include("apps.audit.urls")),
    # ORG
    path("api/org/", include("apps.org.urls")),
    # HR
    path("api/hr/", include("apps.hr.urls")),
]

