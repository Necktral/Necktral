from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.audit.alerts import maybe_alert
from apps.audit.models import AuditEvent


@receiver(post_save, sender=AuditEvent)
def audit_event_alert_handler(sender, instance: AuditEvent, created: bool, **kwargs) -> None:
    if not created:
        return
    maybe_alert(instance)
