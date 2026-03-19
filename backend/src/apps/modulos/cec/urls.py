from __future__ import annotations

from django.urls import path

from .views import (
    CloseRunAdvanceView,
    CloseRunExecuteView,
    CloseRunListCreateView,
    CloseRunSummaryView,
    EvidenceCreateView,
    ExceptionListCreateView,
    ExceptionResolveView,
    HealthView,
)


urlpatterns = [
    path("health/", HealthView.as_view()),
    path("close-runs/", CloseRunListCreateView.as_view()),
    path("close-runs/<uuid:run_id>/advance/", CloseRunAdvanceView.as_view()),
    path("close-runs/<uuid:run_id>/execute/", CloseRunExecuteView.as_view()),
    path("close-runs/<uuid:run_id>/summary/", CloseRunSummaryView.as_view()),
    path("exceptions/", ExceptionListCreateView.as_view()),
    path("exceptions/<uuid:exception_id>/resolve/", ExceptionResolveView.as_view()),
    path("evidence/", EvidenceCreateView.as_view()),
]
