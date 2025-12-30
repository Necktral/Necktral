from django.urls import path
from .views import AuditEventListView

urlpatterns = [
    path('bitacora/', AuditEventListView.as_view(), name='audit-bitacora'),
]
