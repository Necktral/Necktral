from django.urls import path

from .views import SyncBatchView

urlpatterns = [
    path("batch/", SyncBatchView.as_view(), name="sync-batch"),
]
