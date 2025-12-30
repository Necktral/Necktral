from django.urls import path

from .views import ContextEchoView

urlpatterns = [
    path("context/", ContextEchoView.as_view(), name="iam-context"),
]
