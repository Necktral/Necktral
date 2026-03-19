from django.urls import path

from .views import BootstrapInitAdminView, BootstrapStatusView, ContextEchoView

urlpatterns = [
    path("context/", ContextEchoView.as_view(), name="iam-context"),
    path("bootstrap/status/", BootstrapStatusView.as_view(), name="iam-bootstrap-status"),
    path("bootstrap/init-admin/", BootstrapInitAdminView.as_view(), name="iam-bootstrap-init-admin"),
]
