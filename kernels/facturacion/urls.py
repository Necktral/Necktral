from __future__ import annotations

from django.urls import path

from .views import (
    BranchFiscalConfigView,
    DocContingencyResolveView,
    DocContingencyView,
    DocCreateView,
    DocDetailView,
    DocIssueView,
    DocPrintView,
    DocVoidView,
    HealthView,
)

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("fiscal/branch-config/", BranchFiscalConfigView.as_view()),
    path("docs/", DocCreateView.as_view()),
    path("docs/<int:doc_id>/", DocDetailView.as_view()),
    path("docs/<int:doc_id>/issue/", DocIssueView.as_view()),
    path("docs/<int:doc_id>/print/", DocPrintView.as_view()),
    path("docs/<int:doc_id>/contingency/", DocContingencyView.as_view()),
    path("docs/<int:doc_id>/contingency/resolve/", DocContingencyResolveView.as_view()),
    path("docs/<int:doc_id>/void/", DocVoidView.as_view()),
]
