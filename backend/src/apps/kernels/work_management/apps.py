from __future__ import annotations

from django.apps import AppConfig


class WorkManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kernels.work_management"
    label = "work_management"
    verbose_name = "Work Management"
