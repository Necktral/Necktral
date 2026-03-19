from django.urls import path

from .views import MetricsView

urlpatterns = [
    path("", MetricsView.as_view(), name="metrics"),
]
