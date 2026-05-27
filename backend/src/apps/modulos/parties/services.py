from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event

from .models import Party, PartyRole


class _PartyAuditRequest:
    """Contexto liviano para encadenar auditoria de Party por company."""

    def __init__(self, *, request, company) -> None:
        base_req = getattr(request, "_request", request)
        self.company = company
        self.branch = _request_attr(request, base_req, "branch")
        self.ctx = _request_attr(request, base_req, "ctx")
        self.META = _request_attr(request, base_req, "META") or {}
        self.path = _request_attr(request, base_req, "path") or ""
        self.method = _request_attr(request, base_req, "method") or ""
        self.request_id = _request_attr(request, base_req, "request_id") or ""


def _request_attr(request, base_req, name: str):
    if base_req is not None:
        value = getattr(base_req, name, None)
        if value is not None:
            return value
    if request is not None:
        return getattr(request, name, None)
    return None


def _request_company(request):
    if request is None:
        return None
    base_req = getattr(request, "_request", request)
    return _request_attr(request, base_req, "company")


def _same_company(left, right) -> bool:
    return str(getattr(left, "id", left)) == str(getattr(right, "id", right))


def _audit_request_for_company(*, request, company):
    request_company = _request_company(request)
    if request_company is not None and not _same_company(request_company, company):
        raise ValidationError({"company": "Request company no coincide con Party.company."})
    if request_company is not None:
        return request
    return _PartyAuditRequest(request=request, company=company)


def _party_snapshot(party: Party) -> dict[str, Any]:
    return {
        "id": party.id,
        "company_id": party.company_id,
        "party_type": party.party_type,
        "display_name": party.display_name,
        "legal_name": party.legal_name,
        "tax_id": party.tax_id,
        "national_id": party.national_id,
        "email": party.email,
        "phone": party.phone,
        "status": party.status,
    }


def _role_snapshot(role: PartyRole) -> dict[str, Any]:
    return {
        "id": role.id,
        "party_id": role.party_id,
        "company_id": role.party.company_id,
        "role": role.role,
        "is_active": role.is_active,
        "valid_from": role.valid_from.isoformat() if role.valid_from else None,
        "valid_to": role.valid_to.isoformat() if role.valid_to else None,
    }


def create_party(
    *,
    company,
    party_type: str,
    display_name: str,
    legal_name: str = "",
    tax_id: str = "",
    national_id: str = "",
    email: str = "",
    phone: str = "",
    status: str = Party.Status.ACTIVE,
    request=None,
    actor=None,
) -> Party:
    with transaction.atomic():
        party = Party(
            company=company,
            party_type=party_type,
            display_name=display_name,
            legal_name=legal_name,
            tax_id=tax_id,
            national_id=national_id,
            email=email,
            phone=phone,
            status=status,
        )
        party.full_clean()
        party.save()
        write_event(
            request=_audit_request_for_company(request=request, company=party.company),
            module="PARTIES",
            event_type="PARTY_CREATED",
            reason_code="OK",
            actor_user=actor,
            subject_type="PARTY",
            subject_id=str(party.id),
            after_snapshot=_party_snapshot(party),
            metadata={"company_id": str(party.company_id)},
        )
        return party


def update_party(*, party: Party, request=None, actor=None, **updates) -> Party:
    allowed_fields = {
        "party_type",
        "display_name",
        "legal_name",
        "tax_id",
        "national_id",
        "email",
        "phone",
        "status",
    }
    unknown_fields = sorted(set(updates) - allowed_fields)
    if unknown_fields:
        raise ValueError(f"Campos no permitidos para Party: {', '.join(unknown_fields)}")

    with transaction.atomic():
        party = Party.objects.select_for_update().get(pk=party.pk)
        before = _party_snapshot(party)
        for field, value in updates.items():
            setattr(party, field, value)
        party.full_clean()
        party.save()
        write_event(
            request=_audit_request_for_company(request=request, company=party.company),
            module="PARTIES",
            event_type="PARTY_UPDATED",
            reason_code="OK",
            actor_user=actor,
            subject_type="PARTY",
            subject_id=str(party.id),
            before_snapshot=before,
            after_snapshot=_party_snapshot(party),
            metadata={"company_id": str(party.company_id)},
        )
        return party


def assign_party_role(
    *,
    party: Party,
    role: str,
    valid_from=None,
    request=None,
    actor=None,
) -> PartyRole:
    with transaction.atomic():
        party = Party.objects.select_for_update().get(pk=party.pk)
        active_exists = PartyRole.objects.select_for_update().filter(party=party, role=role, is_active=True).exists()
        if active_exists:
            raise ValidationError({"role": "La Party ya tiene este rol activo."})

        party_role = PartyRole(party=party, role=role, valid_from=valid_from or timezone.now())
        party_role.full_clean()
        party_role.save()
        write_event(
            request=_audit_request_for_company(request=request, company=party.company),
            module="PARTIES",
            event_type="PARTY_ROLE_ASSIGNED",
            reason_code="OK",
            actor_user=actor,
            subject_type="PARTY_ROLE",
            subject_id=str(party_role.id),
            after_snapshot=_role_snapshot(party_role),
            metadata={"company_id": str(party.company_id), "party_id": str(party.id)},
        )
        return party_role


def revoke_party_role(
    *,
    party: Party,
    role: str,
    valid_to=None,
    request=None,
    actor=None,
) -> PartyRole:
    with transaction.atomic():
        party = Party.objects.select_for_update().get(pk=party.pk)
        party_role = (
            PartyRole.objects.select_for_update().filter(party=party, role=role, is_active=True).order_by("id").first()
        )
        if party_role is None:
            raise ValidationError({"role": "La Party no tiene este rol activo."})

        before = _role_snapshot(party_role)
        party_role.is_active = False
        party_role.valid_to = valid_to or timezone.now()
        party_role.full_clean()
        party_role.save()
        write_event(
            request=_audit_request_for_company(request=request, company=party.company),
            module="PARTIES",
            event_type="PARTY_ROLE_REVOKED",
            reason_code="OK",
            actor_user=actor,
            subject_type="PARTY_ROLE",
            subject_id=str(party_role.id),
            before_snapshot=before,
            after_snapshot=_role_snapshot(party_role),
            metadata={"company_id": str(party.company_id), "party_id": str(party.id)},
        )
        return party_role
