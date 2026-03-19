from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.reports.models import DatasetCache, ReportExport


class Command(BaseCommand):
    help = "Limpia cache datasets y exports vencidos de reports."

    def handle(self, *args, **options):
        now = timezone.now()
        cache_deleted, _ = DatasetCache.objects.filter(expires_at__lt=now).delete()
        export_deleted, _ = ReportExport.objects.filter(retention_until__lt=now).delete()
        self.stdout.write(self.style.SUCCESS(f"cache_deleted={cache_deleted} export_deleted={export_deleted}"))

