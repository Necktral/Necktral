from __future__ import annotations

from django.urls import path

from .views import (
    DeviceEnrollView,
    DeviceRevokeView,
    EnrollmentChallengeCreateView,
    SyncBatchView,
    DeviceListView,
)

urlpatterns = [
    path("enrollment/challenges/", EnrollmentChallengeCreateView.as_view(), name="sync_enroll_challenge_create"),
    path("enroll/", DeviceEnrollView.as_view(), name="sync_device_enroll"),
    path("devices/<uuid:device_id>/revoke/", DeviceRevokeView.as_view(), name="sync_device_revoke"),
    path("batch/", SyncBatchView.as_view(), name="sync_batch"),
    path("devices/", DeviceListView.as_view(), name="sync_device_list"),
]
