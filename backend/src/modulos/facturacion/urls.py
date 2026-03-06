from __future__ import annotations

from django.urls import path

from .views import HealthView, DocCreateView, DocDetailView, DocIssueView, DocVoidView

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("docs/", DocCreateView.as_view()),
    path("docs/<int:doc_id>/", DocDetailView.as_view()),
    path("docs/<int:doc_id>/issue/", DocIssueView.as_view()),
    path("docs/<int:doc_id>/void/", DocVoidView.as_view()),
]
