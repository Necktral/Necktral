from __future__ import annotations

from django.urls import path

from .views import HealthView, InboxAckView, InboxListView, OutboxListView, OutboxMarkSentView


urlpatterns = [
    path("health/", HealthView.as_view()),
    path("outbox/", OutboxListView.as_view()),
    path("outbox/<uuid:event_id>/sent/", OutboxMarkSentView.as_view()),
    path("inbox/", InboxListView.as_view()),
    path("inbox/<int:inbox_id>/ack/", InboxAckView.as_view()),
]
