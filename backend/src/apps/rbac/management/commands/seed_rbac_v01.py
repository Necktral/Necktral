from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.audit.writer import write_event
from apps.rbac.seed_v01 import seed_rbac_v01


class Command(BaseCommand):
    help = "Seed idempotente RBAC v0.1 (roles/permisos estándar)."

    def handle(self, *args, **options):
        result = seed_rbac_v01()

        # Audit (SYSTEM)
        write_event(
            request=None,
            module="RBAC",
            event_type="RBAC_SEEDED_V01",
            reason_code="OK",
            actor_user=None,
            subject_type="",
            subject_id="",
            metadata={
                "roles_created": result.roles_created,
                "roles_updated": result.roles_updated,
                "perms_created": result.perms_created,
                "perms_updated": result.perms_updated,
                "roleperms_created": result.roleperms_created,
            },
        )

        self.stdout.write(self.style.SUCCESS("RBAC v0.1 seeded OK"))
        self.stdout.write(str(result))
