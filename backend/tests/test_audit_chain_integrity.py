import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test.utils import override_settings

from apps.audit.integrity import verify_queryset
from apps.audit.models import AuditEvent
from apps.audit.writer import write_event

User = get_user_model()


@pytest.mark.django_db
def test_audit_chain_verifier_passes_for_writer_events():
    user = User.objects.create_user(username="u_chain", password="pass12345")
    rf = RequestFactory()

    req = rf.post(
        "/api/auth/login/",
        data={"username": "u_chain"},
        content_type="application/json",
        HTTP_USER_AGENT="pytest",
    )
    req.META["REMOTE_ADDR"] = "127.0.0.1"

    write_event(
        request=req,
        event_type="AUTH_LOGIN_SUCCESS",
        reason_code="",
        actor_user=user,
        subject_type="USER",
        subject_id=str(user.id),
    )
    write_event(
        request=req,
        event_type="AUTH_LOGOUT",
        reason_code="",
        actor_user=user,
        subject_type="USER",
        subject_id=str(user.id),
    )

    qs = AuditEvent.objects.filter(partition_key="SYSTEM")
    report = verify_queryset(qs)
    assert report.ok is True
    assert report.errors == []


@pytest.mark.django_db
def test_audit_chain_verifier_detects_payload_tampering():
    user = User.objects.create_user(username="u_tamper", password="pass12345")
    rf = RequestFactory()

    req = rf.post(
        "/api/auth/login/",
        data={"username": "u_tamper"},
        content_type="application/json",
        HTTP_USER_AGENT="pytest",
    )
    req.META["REMOTE_ADDR"] = "127.0.0.1"

    ev = write_event(
        request=req,
        event_type="AUTH_LOGIN_SUCCESS",
        reason_code="",
        actor_user=user,
        subject_type="USER",
        subject_id=str(user.id),
    )

    # Tamper: cambia metadata sin recalcular hashes/firma
    ev.metadata["tampered"] = True
    ev.save(update_fields=["metadata"])

    report = verify_queryset(AuditEvent.objects.filter(partition_key="SYSTEM"))
    assert report.ok is False
    assert any(e.code == "EVENT_HASH_MISMATCH" for e in report.errors)


@pytest.mark.django_db
def test_audit_chain_verifier_detects_prev_hash_break():
    user = User.objects.create_user(username="u_prev", password="pass12345")
    rf = RequestFactory()

    req = rf.post(
        "/api/auth/login/",
        data={"username": "u_prev"},
        content_type="application/json",
        HTTP_USER_AGENT="pytest",
    )
    req.META["REMOTE_ADDR"] = "127.0.0.1"

    write_event(
        request=req,
        event_type="AUTH_LOGIN_SUCCESS",
        reason_code="",
        actor_user=user,
        subject_type="USER",
        subject_id=str(user.id),
    )
    ev2 = write_event(
        request=req,
        event_type="AUTH_LOGOUT",
        reason_code="",
        actor_user=user,
        subject_type="USER",
        subject_id=str(user.id),
    )

    ev2.prev_event_hash = "0" * 64
    ev2.save(update_fields=["prev_event_hash"])

    report = verify_queryset(AuditEvent.objects.filter(partition_key="SYSTEM"))
    assert report.ok is False
    # Cambiar prev_event_hash sin recalcular hashes/firma invalida el payload canónico,
    # por lo que deben saltar mismatches criptográficos (más fuerte que solo la topología).
    assert any(e.code == "EVENT_HASH_MISMATCH" for e in report.errors)
    assert any(e.code == "SIGNATURE_MISMATCH" for e in report.errors)


@pytest.mark.django_db
@override_settings(AUDIT_HMAC_KEYS="k2:secret2,k1:secret1", AUDIT_HMAC_KEY="legacy-secret")
def test_audit_chain_verifier_accepts_rotated_keys():
    user = User.objects.create_user(username="u_rotate", password="pass12345")
    rf = RequestFactory()

    req = rf.post(
        "/api/auth/login/",
        data={"username": "u_rotate"},
        content_type="application/json",
        HTTP_USER_AGENT="pytest",
    )
    req.META["REMOTE_ADDR"] = "127.0.0.1"

    ev = write_event(
        request=req,
        event_type="AUTH_LOGIN_SUCCESS",
        reason_code="",
        actor_user=user,
        subject_type="USER",
        subject_id=str(user.id),
    )
    assert ev.signature_key_id == "k2"

    report = verify_queryset(AuditEvent.objects.filter(partition_key="SYSTEM"))
    assert report.ok is True

    # Compatibilidad: eventos sin key_id deben validar con cualquier llave activa.
    ev.signature_key_id = ""
    ev.save(update_fields=["signature_key_id"])
    report2 = verify_queryset(AuditEvent.objects.filter(partition_key="SYSTEM"))
    assert report2.ok is True
