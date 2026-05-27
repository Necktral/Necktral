from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory

from apps.kernels.accounting.models import EconomicEvent, JournalDraft
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.parties import services as party_services
from apps.modulos.parties.admin import PartyAdmin, PartyRoleAdmin
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.parties.services import assign_party_role, create_party, revoke_party_role, update_party

User = get_user_model()


def _company():
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name="Holding",
        code="H",
        is_active=True,
    )
    return OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name="Company",
        code="C",
        is_active=True,
    )


def _assert_no_financial_side_effects():
    assert OutboxEvent.objects.count() == 0
    assert EconomicEvent.objects.count() == 0
    assert JournalDraft.objects.count() == 0


def _audit_failure(*args, **kwargs):
    raise RuntimeError("audit writer unavailable")


def _admin_request(method: str = "get"):
    request = getattr(RequestFactory(), method)("/admin/modulos/parties/party/")
    request.user = User.objects.create_superuser(
        username=f"party_admin_{User.objects.count()}",
        email=f"party_admin_{User.objects.count()}@example.com",
        password="test-pass",
    )
    return request


@pytest.mark.django_db
def test_create_party_service_emits_audit_event_only():
    company = _company()

    party = create_party(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name=" Cliente Servicio ",
        tax_id=" ruc-svc ",
        email=" SVC@EXAMPLE.COM ",
    )

    assert party.display_name == "Cliente Servicio"
    assert party.tax_id == "RUC-SVC"
    assert party.email == "svc@example.com"

    event = AuditEvent.objects.get(event_type="PARTY_CREATED")
    assert event.module == "PARTIES"
    assert event.subject_type == "PARTY"
    assert event.subject_id == str(party.id)
    assert event.partition_key == f"COMPANY:{company.id}"
    assert event.metadata["company_id"] == str(company.id)
    assert event.after_snapshot["company_id"] == company.id
    assert not AuditEvent.objects.filter(partition_key="SYSTEM", event_type__startswith="PARTY").exists()
    _assert_no_financial_side_effects()


@pytest.mark.django_db
def test_update_party_service_emits_audit_event_only():
    company = _company()
    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name="Cliente Viejo",
        email="old@example.com",
    )

    updated = update_party(party=party, display_name=" Cliente Nuevo ", email=" NEW@EXAMPLE.COM ")

    assert updated.display_name == "Cliente Nuevo"
    assert updated.email == "new@example.com"

    event = AuditEvent.objects.get(event_type="PARTY_UPDATED")
    assert event.module == "PARTIES"
    assert event.partition_key == f"COMPANY:{company.id}"
    assert event.metadata["company_id"] == str(company.id)
    assert event.before_snapshot["display_name"] == "Cliente Viejo"
    assert event.after_snapshot["display_name"] == "Cliente Nuevo"
    _assert_no_financial_side_effects()


@pytest.mark.django_db
def test_assign_and_revoke_party_role_services_emit_audit_events_only():
    company = _company()
    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name="Proveedor Servicio",
    )

    customer_role = assign_party_role(party=party, role=PartyRole.Role.CUSTOMER)
    supplier_role = assign_party_role(party=party, role=PartyRole.Role.SUPPLIER)

    assert customer_role.is_active is True
    assert supplier_role.is_active is True
    assert party.roles.filter(is_active=True).count() == 2

    with pytest.raises(ValidationError):
        assign_party_role(party=party, role=PartyRole.Role.CUSTOMER)

    revoked = revoke_party_role(party=party, role=PartyRole.Role.CUSTOMER)
    assert revoked.is_active is False
    assert revoked.valid_to is not None

    reassigned = assign_party_role(party=party, role=PartyRole.Role.CUSTOMER)
    assert reassigned.id != revoked.id
    assert reassigned.is_active is True
    assert party.roles.filter(role=PartyRole.Role.CUSTOMER, is_active=True).count() == 1

    event_types = set(AuditEvent.objects.values_list("event_type", flat=True))
    assert "PARTY_ROLE_ASSIGNED" in event_types
    assert "PARTY_ROLE_REVOKED" in event_types
    assigned_event = AuditEvent.objects.filter(event_type="PARTY_ROLE_ASSIGNED").order_by("event_id").first()
    assert assigned_event.partition_key == f"COMPANY:{company.id}"
    assert assigned_event.metadata["company_id"] == str(company.id)
    assert assigned_event.metadata["party_id"] == str(party.id)
    assert assigned_event.subject_type == "PARTY_ROLE"
    assert not AuditEvent.objects.filter(partition_key="SYSTEM", event_type__startswith="PARTY").exists()
    _assert_no_financial_side_effects()


@pytest.mark.django_db
def test_party_services_reject_request_company_mismatch():
    company = _company()
    other_company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=company.parent,
        name="Other Company",
        code="OC",
        is_active=True,
    )
    request = SimpleNamespace(company=other_company, META={}, path="/parties", method="POST", request_id="req-1")

    with pytest.raises(ValidationError):
        create_party(
            company=company,
            party_type=Party.PartyType.NATURAL,
            display_name="Cross Company",
            request=request,
        )

    assert Party.objects.count() == 0
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_create_party_rolls_back_when_audit_writer_fails(monkeypatch):
    company = _company()
    monkeypatch.setattr(party_services, "write_event", _audit_failure)

    with pytest.raises(RuntimeError):
        create_party(
            company=company,
            party_type=Party.PartyType.NATURAL,
            display_name="Rollback Party",
        )

    assert Party.objects.count() == 0
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_update_party_rolls_back_when_audit_writer_fails(monkeypatch):
    company = _company()
    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name="Nombre Original",
    )
    monkeypatch.setattr(party_services, "write_event", _audit_failure)

    with pytest.raises(RuntimeError):
        update_party(party=party, display_name="Nombre Cambiado")

    party.refresh_from_db()
    assert party.display_name == "Nombre Original"
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_assign_party_role_rolls_back_when_audit_writer_fails(monkeypatch):
    company = _company()
    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name="Proveedor Rollback",
    )
    monkeypatch.setattr(party_services, "write_event", _audit_failure)

    with pytest.raises(RuntimeError):
        assign_party_role(party=party, role=PartyRole.Role.SUPPLIER)

    assert PartyRole.objects.count() == 0
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_revoke_party_role_rolls_back_when_audit_writer_fails(monkeypatch):
    company = _company()
    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name="Proveedor Revocable",
    )
    party_role = PartyRole.objects.create(party=party, role=PartyRole.Role.SUPPLIER)
    monkeypatch.setattr(party_services, "write_event", _audit_failure)

    with pytest.raises(RuntimeError):
        revoke_party_role(party=party, role=PartyRole.Role.SUPPLIER)

    party_role.refresh_from_db()
    assert party_role.is_active is True
    assert party_role.valid_to is None
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_party_admin_is_read_only_and_blocks_direct_writes():
    company = _company()
    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name="Admin Read Only",
    )
    model_admin = PartyAdmin(Party, admin.AdminSite(name="party-admin-test"))
    get_request = _admin_request("get")
    post_request = _admin_request("post")

    assert model_admin.has_add_permission(get_request) is False
    assert model_admin.has_change_permission(get_request, party) is True
    assert model_admin.has_change_permission(post_request, party) is False
    assert model_admin.has_delete_permission(get_request, party) is False
    assert "delete_selected" not in model_admin.get_actions(get_request)
    assert set(model_admin.get_readonly_fields(get_request, party)) >= {
        "company",
        "party_type",
        "display_name",
        "legal_name",
        "tax_id",
        "national_id",
        "email",
        "phone",
        "status",
        "created_at",
        "updated_at",
    }

    with pytest.raises(PermissionDenied):
        model_admin.save_model(post_request, party, form=None, change=True)
    with pytest.raises(PermissionDenied):
        model_admin.delete_model(post_request, party)
    with pytest.raises(PermissionDenied):
        model_admin.delete_queryset(post_request, Party.objects.filter(pk=party.pk))


@pytest.mark.django_db
def test_party_role_admin_is_read_only_and_blocks_direct_writes():
    company = _company()
    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name="Admin Role Read Only",
    )
    party_role = PartyRole.objects.create(party=party, role=PartyRole.Role.CUSTOMER)
    model_admin = PartyRoleAdmin(PartyRole, admin.AdminSite(name="party-role-admin-test"))
    get_request = _admin_request("get")
    post_request = _admin_request("post")

    assert model_admin.has_add_permission(get_request) is False
    assert model_admin.has_change_permission(get_request, party_role) is True
    assert model_admin.has_change_permission(post_request, party_role) is False
    assert model_admin.has_delete_permission(get_request, party_role) is False
    assert "delete_selected" not in model_admin.get_actions(get_request)
    assert set(model_admin.get_readonly_fields(get_request, party_role)) >= {
        "party",
        "role",
        "is_active",
        "valid_from",
        "valid_to",
        "created_at",
        "updated_at",
    }

    with pytest.raises(PermissionDenied):
        model_admin.save_model(post_request, party_role, form=None, change=True)
    with pytest.raises(PermissionDenied):
        model_admin.delete_model(post_request, party_role)
    with pytest.raises(PermissionDenied):
        model_admin.delete_queryset(post_request, PartyRole.objects.filter(pk=party_role.pk))
