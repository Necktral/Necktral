from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.rbac.models import Permission
from apps.rbac.permissions_registry import PERMISSIONS_REGISTRY
from django.utils import timezone


class Command(BaseCommand):
    help = "Diagnostico RBAC: permisos sin registry, registry sin seed, expiraciones."

    def handle(self, *args, **options):
        codes_db = set(Permission.objects.values_list("code", flat=True))
        codes_reg = set(PERMISSIONS_REGISTRY.keys())

        missing_registry = sorted(codes_db - codes_reg)
        missing_db = sorted(codes_reg - codes_db)
        today = timezone.now().date()
        expired = sorted(
            [
                code
                for code, meta in PERMISSIONS_REGISTRY.items()
                if getattr(meta, "expires_at", None) is not None and meta.expires_at < today
            ]
        )

        if missing_registry:
            self.stdout.write("Permisos sin registry:")
            for code in missing_registry:
                self.stdout.write(f"- {code}")

        if missing_db:
            self.stdout.write("Permisos en registry pero no en DB (seed faltante):")
            for code in missing_db:
                self.stdout.write(f"- {code}")

        if expired:
            self.stdout.write("Permisos expirados en registry:")
            for code in expired:
                self.stdout.write(f"- {code}")

        if missing_registry or missing_db or expired:
            raise SystemExit(2)

        self.stdout.write("RBAC doctor OK: registry y DB alineados")
