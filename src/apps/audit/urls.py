from django.urls import path
from .views import AuditEventListView, AuditEventDetailView

urlpatterns = [
    path('bitacora/', AuditEventListView.as_view(), name='audit-bitacora'),
    path('events/<uuid:event_id>/', AuditEventDetailView.as_view(), name='audit-event-detail'),
]
