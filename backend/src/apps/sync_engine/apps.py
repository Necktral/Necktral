from __future__ import annotations

from django.apps import AppConfig


class SyncEngineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sync_engine"
    verbose_name = "Sync Engine (Offline-first)"
