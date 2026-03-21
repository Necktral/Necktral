from __future__ import annotations

from django.urls import path

from .views import (
    DashboardCatalogView,
    DashboardDrilldownView,
    DashboardWorkspaceDetailView,
    DashboardWorkspaceQueryView,
)

urlpatterns = [
    path("catalog/", DashboardCatalogView.as_view()),
    path("workspaces/<str:workspace_code>/", DashboardWorkspaceDetailView.as_view()),
    path("workspaces/<str:workspace_code>/query/", DashboardWorkspaceQueryView.as_view()),
    path("drilldown/", DashboardDrilldownView.as_view()),
]
