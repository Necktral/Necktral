from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.audit.writer import write_event
from apps.rbac.models import RoleAssignment


@receiver(post_save, sender=RoleAssignment)
def role_assignment_audit_handler(sender, instance: RoleAssignment, created: bool, **kwargs) -> None:
    if not created or not instance.is_active:
        return

    write_event(
        request=None,
        module="RBAC",
        event_type="RBAC_ROLE_ASSIGNED",
        reason_code="RBAC_OK",
        actor_user=instance.granted_by,
        subject_type="USER",
        subject_id=str(instance.user_id),
        metadata={
            "role": getattr(instance.role, "name", ""),
            "org_unit_id": str(instance.org_unit_id),
            "origin": instance.origin,
            "origin_ref": instance.origin_ref,
        },
    )
