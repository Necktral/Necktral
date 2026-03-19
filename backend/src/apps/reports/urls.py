from __future__ import annotations

from django.urls import path

from .views import (
    HealthView,
    ReportDefinitionListCreateView,
    ReportExportCreateView,
    ReportExportDetailView,
    ReportReadAuditListView,
    ReportRunExportCompatView,
    ReportRunDetailView,
    ReportRunCancelView,
    ReportRunListCreateView,
    ReportRunRetryView,
    ReportSourceListView,
)

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("definitions/", ReportDefinitionListCreateView.as_view()),
    path("runs/", ReportRunListCreateView.as_view()),
    path("runs/<str:run_id>/", ReportRunDetailView.as_view()),
    path("runs/<str:run_id>/cancel/", ReportRunCancelView.as_view()),
    path("runs/<str:run_id>/retry/", ReportRunRetryView.as_view()),
    path("runs/<str:run_id>/export/", ReportRunExportCompatView.as_view()),
    path("exports/", ReportExportCreateView.as_view()),
    path("exports/<str:export_id>/", ReportExportDetailView.as_view()),
    path("read-audit/", ReportReadAuditListView.as_view()),
    path("sources/", ReportSourceListView.as_view()),
]
