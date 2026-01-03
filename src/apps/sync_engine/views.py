
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from django.db.models import Q
import uuid
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.writer import write_event
from apps.common.permissions import rbac_permission
from apps.iam.models import OrgUnit

from .models import Device, DeviceEnrollmentChallenge
from .serializers import EnrollmentChallengeCreateIn, DeviceEnrollIn, SyncBatchIn
from .signing import public_key_from_b64
from .services import process_batch, resolve_device


class EnrollmentChallengeCreateView(APIView):
    """
    POST /api/sync/enrollment/challenges/
    Requiere JWT + contexto (X-Company-Id) porque usa rbac_permission.
    """
    permission_classes = [rbac_permission("sync.device.enroll")]

    def post(self, request):
        ser = EnrollmentChallengeCreateIn(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # Contexto activo (inyectado por tu JWTAuthWithOrgContext)
        company = getattr(request, "company", None)
        if company is None:
            raise ParseError("Falta contexto company (X-Company-Id).")

        company_id = int(data.get("company_id") or company.id)
        if company_id != company.id:
            raise ParseError("company_id debe coincidir con X-Company-Id en esta fase.")

        branch_id = data.get("branch_id", None)
        branch = None
        if branch_id is not None:
            branch = OrgUnit.objects.filter(
                id=int(branch_id),
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=company,
                is_active=True,
            ).first()
            if not branch:
                raise NotFound("Sucursal no encontrada o inactiva.")

        expires_in = int(data.get("expires_in_minutes") or 15)
        expires_at = timezone.now() + timedelta(minutes=expires_in)

        code_plain = DeviceEnrollmentChallenge.generate_code()
        code_hash = DeviceEnrollmentChallenge.sha256_hex(code_plain)

        ch = DeviceEnrollmentChallenge.objects.create(
            company=company,
            branch=branch,
            enrollment_code_hash=code_hash,
            expires_at=expires_at,
            created_by_user=request.user,
            label_hint=str(data.get("label_hint") or ""),
        )

        write_event(
            request=request,
            event_type="SYNC_ENROLL_CHALLENGE_CREATED",
            reason_code="SYNC_OK",
            actor_user=request.user,
            subject_type="DEVICE",
            subject_id="",
            device_id="",
            offline_mode=False,
            metadata={"challenge_id": str(ch.id), "company_id": company.id, "branch_id": getattr(branch, "id", None)},
        )

        return Response(
            {
                "challenge_id": str(ch.id),
                "enrollment_code": code_plain,  # solo se entrega aquí
                "expires_at": ch.expires_at.isoformat(),
                "company_id": company.id,
                "branch_id": getattr(branch, "id", None),
            },
            status=201,
        )


class DeviceEnrollView(APIView):
    """
    POST /api/sync/enroll/
    No requiere JWT: el secreto es el enrollment_code (one-time).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ser = DeviceEnrollIn(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        code_plain = str(data["enrollment_code"])
        code_hash = DeviceEnrollmentChallenge.sha256_hex(code_plain)

        ch = DeviceEnrollmentChallenge.objects.select_related("company", "branch").filter(
            enrollment_code_hash=code_hash
        ).first()
        if not ch:
            raise PermissionDenied("Código inválido.")
        if not ch.is_valid_now():
            raise PermissionDenied("Código expirado o ya usado.")

        try:
            pk_raw = public_key_from_b64(data["public_key_b64"])
        except Exception as e:
            raise ParseError(str(e))

        label = str(data.get("label") or ch.label_hint or "")
        meta = data.get("meta") or {}

        device = Device.objects.create(
            company=ch.company,
            branch=ch.branch,
            label=label,
            status=Device.Status.ACTIVE,
            public_key=bytes(pk_raw),
            meta=meta,
            enrolled_by_user=ch.created_by_user,
        )

        ch.used_at = timezone.now()
        ch.used_by_device = device
        ch.save(update_fields=["used_at", "used_by_device"])

        write_event(
            request=request,
            event_type="SYNC_DEVICE_ENROLLED",
            reason_code="SYNC_OK",
            actor_user=None,
            subject_type="DEVICE",
            subject_id=str(device.id),
            device_id=str(device.id),
            offline_mode=True,
            metadata={
                "company_id": device.company_id,
                "branch_id": device.branch_id,
                "label": device.label,
            },
        )

        from apps.sync_engine.services import get_policy
        policy = get_policy()
        return Response(
            {
                "device_id": str(device.id),
                "device_status": device.status,
                "company_id": device.company_id,
                "branch_id": device.branch_id,
                "server_time": timezone.now().isoformat(),
                "policy": {
                    "max_commands_per_batch": policy.max_commands_per_batch,
                    "max_payload_bytes": policy.max_payload_bytes,
                    "max_device_clock_skew_seconds": policy.max_device_clock_skew_seconds,
                    "seq_tolerant": policy.seq_tolerant,
                },
            },
            status=201,
        )


class DeviceRevokeView(APIView):
    """
    POST /api/sync/devices/<device_id>/revoke/
    Requiere JWT + permiso.
    """
    permission_classes = [rbac_permission("sync.device.revoke")]

    def post(self, request, device_id: str):
        company = getattr(request, "company", None)
        if company is None:
            raise ParseError("Falta contexto company (X-Company-Id).")

        device = Device.objects.filter(id=device_id, company=company).first()
        if not device:
            raise NotFound("Device no encontrado en esta company.")

        device.revoke()

        write_event(
            request=request,
            event_type="SYNC_DEVICE_REVOKED",
            reason_code="SYNC_OK",
            actor_user=request.user,
            subject_type="DEVICE",
            subject_id=str(device.id),
            device_id=str(device.id),
            offline_mode=False,
            metadata={"company_id": device.company_id, "branch_id": device.branch_id},
        )

        return Response({"device_id": str(device.id), "status": device.status}, status=200)


class DeviceListView(APIView):
    """
    GET /api/sync/devices/
    Requiere JWT + permiso.
    Política: quien puede revocar, puede listar.
    """
    permission_classes = [rbac_permission("sync.device.revoke")]

    def get(self, request):
        company = getattr(request, "company", None)
        if company is None:
            raise ParseError("Falta contexto company (X-Company-Id).")

        qs = Device.objects.filter(company=company).order_by("-created_at")

        status_param = (request.query_params.get("status") or "").strip()
        if status_param:
            qs = qs.filter(status=status_param)

        q = (request.query_params.get("q") or "").strip()
        if q:
            filt = Q(label__icontains=q)
            try:
                filt |= Q(id=uuid.UUID(q))
            except Exception:
                pass
            qs = qs.filter(filt)

        try:
            limit = int(request.query_params.get("limit") or 50)
        except Exception:
            limit = 50
        try:
            offset = int(request.query_params.get("offset") or 0)
        except Exception:
            offset = 0

        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        total = qs.count()
        rows = qs[offset : offset + limit]

        results = [
            {
                "id": str(d.id),
                "label": d.label,
                "status": d.status,
                "company_id": d.company_id,
                "branch_id": d.branch_id,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "revoked_at": d.revoked_at.isoformat() if d.revoked_at else None,
                "last_seen_at": d.last_seen_at.isoformat() if getattr(d, "last_seen_at", None) else None,
                "last_accepted_sequence": getattr(d, "last_accepted_sequence", None),
            }
            for d in rows
        ]

        return Response({"count": total, "limit": limit, "offset": offset, "results": results}, status=200)


class SyncBatchView(APIView):
    """
    POST /api/sync/batch/
    Device-auth (X-Device-Id) + firma por comando.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ser = SyncBatchIn(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        hdr_device_id = request.headers.get("X-Device-Id")
        body_device_id = data.get("device_id")

        if hdr_device_id:
            device_id = hdr_device_id.strip()
        elif body_device_id:
            device_id = str(body_device_id)
        else:
            raise PermissionDenied("X-Device-Id requerido.")

        device = resolve_device(device_id=device_id)

        out = process_batch(
            request=request._request if hasattr(request, "_request") else request,
            actor_user=getattr(request, "user", None),
            device=device,
            batch_id=data["batch_id"],
            sent_at=data.get("sent_at"),
            commands=data["commands"],
        )
        return Response(out, status=200)
