from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone

from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.integration.services import dispatch_outbox_events


@pytest.mark.django_db
def test_outbox_dispatcher_marks_sent_on_success():
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"ok": True},
    )
    fixed_now = timezone.make_aware(datetime(2026, 3, 8, 8, 0, 0))
    summary = dispatch_outbox_events(sender=lambda _: None, limit=10, now=fixed_now)
    ev.refresh_from_db()

    assert summary.attempted == 1
    assert summary.sent == 1
    assert summary.retried == 0
    assert summary.failed == 0
    assert ev.status == OutboxEvent.Status.SENT
    assert ev.attempt_count == 1
    assert ev.published_at == fixed_now


@pytest.mark.django_db
def test_outbox_dispatcher_retries_with_exponential_backoff():
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunExecuted",
        payload={"ok": True},
    )
    fixed_now = timezone.make_aware(datetime(2026, 3, 8, 9, 0, 0))

    def _fail(_):
        raise RuntimeError("temporary broker error")

    summary = dispatch_outbox_events(sender=_fail, limit=10, now=fixed_now)
    ev.refresh_from_db()

    assert summary.attempted == 1
    assert summary.sent == 0
    assert summary.retried == 1
    assert summary.failed == 0
    assert ev.status == OutboxEvent.Status.PENDING
    assert ev.attempt_count == 1
    assert ev.next_attempt_at == fixed_now + timedelta(minutes=2)
    assert "temporary broker error" in ev.last_error


@pytest.mark.django_db
def test_outbox_dispatcher_moves_to_failed_after_max_attempts():
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunExecuted",
        payload={"ok": True},
        attempt_count=4,
    )
    fixed_now = timezone.make_aware(datetime(2026, 3, 8, 10, 0, 0))

    def _fail(_):
        raise RuntimeError("still failing")

    summary = dispatch_outbox_events(sender=_fail, limit=10, now=fixed_now)
    ev.refresh_from_db()

    assert summary.attempted == 1
    assert summary.sent == 0
    assert summary.retried == 0
    assert summary.failed == 1
    assert ev.status == OutboxEvent.Status.FAILED
    assert ev.attempt_count == 5
    assert ev.next_attempt_at is None


@pytest.mark.django_db
def test_inbox_idempotency_unique_per_event_consumer():
    event_id = uuid.uuid4()
    InboxEvent.objects.create(
        event_id=event_id,
        consumer="accounting.projector",
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"x": 1},
    )
    with pytest.raises(IntegrityError):
        InboxEvent.objects.create(
            event_id=event_id,
            consumer="accounting.projector",
            source_module="CEC",
            event_type="CloseRunPackaged",
            payload={"x": 1},
        )


@pytest.mark.django_db
def test_dispatch_outbox_command_dispatches_pending_events():
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunExecuted",
        payload={"ok": True},
    )
    stdout = StringIO()
    call_command("dispatch_outbox", limit=10, stdout=stdout)
    ev.refresh_from_db()

    assert ev.status == OutboxEvent.Status.SENT
    output = stdout.getvalue()
    assert "attempted=1" in output
